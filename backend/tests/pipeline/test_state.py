"""Tests for the pipeline state machine (app/pipeline/state.py)."""

import pytest

from app.pipeline.errors import InvalidTransitionError
from app.pipeline.state import (
    ALLOWED_TRANSITIONS,
    FILE_PATH,
    URL_PATH,
    ArtifactKind,
    Checkpoint,
    PipelinePhase,
    TaskStatus,
    next_phases,
    resume_point,
    validate_completion,
    validate_transition,
)


class TestEnums:
    def test_task_status_values(self) -> None:
        assert TaskStatus.pending.value == "pending"
        assert TaskStatus.running.value == "running"
        assert TaskStatus.complete.value == "complete"
        assert TaskStatus.failed.value == "failed"
        assert TaskStatus.cancelled.value == "cancelled"

    def test_pipeline_phase_values(self) -> None:
        assert PipelinePhase.fetching.value == "fetching"
        assert PipelinePhase.subtitle.value == "subtitle"
        assert PipelinePhase.audio.value == "audio"
        assert PipelinePhase.transcribe.value == "transcribe"
        assert PipelinePhase.notegen.value == "notegen"

    def test_artifact_kinds(self) -> None:
        assert {k.value for k in ArtifactKind} == {
            "video_meta",
            "subtitle",
            "transcript",
            "notes_draft",
        }


class TestTransitionMatrix:
    def test_full_legal_transition_matrix(self) -> None:
        """Every transition in ALLOWED_TRANSITIONS validates without raising."""
        for src, dsts in ALLOWED_TRANSITIONS.items():
            for dst in dsts:
                validate_transition(src, dst)  # must not raise

    def test_start_transitions(self) -> None:
        assert ALLOWED_TRANSITIONS[None] == {
            PipelinePhase.fetching,
            PipelinePhase.audio,
        }

    def test_subtitle_conditional_skip(self) -> None:
        # miss -> audio; hit -> notegen (bypasses audio + transcribe)
        assert ALLOWED_TRANSITIONS[PipelinePhase.subtitle] == {
            PipelinePhase.audio,
            PipelinePhase.notegen,
        }

    def test_linear_tail(self) -> None:
        assert ALLOWED_TRANSITIONS[PipelinePhase.fetching] == {PipelinePhase.subtitle}
        assert ALLOWED_TRANSITIONS[PipelinePhase.audio] == {PipelinePhase.transcribe}
        assert ALLOWED_TRANSITIONS[PipelinePhase.transcribe] == {PipelinePhase.notegen}
        assert ALLOWED_TRANSITIONS[PipelinePhase.notegen] == frozenset()

    @pytest.mark.parametrize(
        ("src", "dst"),
        [
            (None, PipelinePhase.transcribe),  # start must not jump mid-path
            (None, PipelinePhase.notegen),
            (PipelinePhase.fetching, PipelinePhase.audio),  # must go through subtitle
            (PipelinePhase.fetching, PipelinePhase.notegen),
            (PipelinePhase.audio, PipelinePhase.notegen),  # must transcribe first
            (PipelinePhase.audio, PipelinePhase.fetching),  # no backwards
            (PipelinePhase.transcribe, PipelinePhase.subtitle),
            (PipelinePhase.transcribe, PipelinePhase.audio),  # no backwards
            (PipelinePhase.notegen, PipelinePhase.fetching),
            (PipelinePhase.notegen, PipelinePhase.notegen),  # no self-loop
            (PipelinePhase.subtitle, PipelinePhase.fetching),
        ],
    )
    def test_illegal_transitions_rejected(
        self, src: PipelinePhase | None, dst: PipelinePhase
    ) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_transition(src, dst)

    def test_error_carries_src_and_dst(self) -> None:
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(PipelinePhase.audio, PipelinePhase.notegen)
        assert exc_info.value.src is PipelinePhase.audio
        assert exc_info.value.dst is PipelinePhase.notegen


class TestNextPhases:
    def test_url_path_start(self) -> None:
        # Start phases are the transition-table start set intersected with
        # the path: URL path can only begin at fetching (audio is a valid
        # global start but not part of the URL sequence order).
        assert next_phases(URL_PATH, None) == (
            PipelinePhase.fetching,
            PipelinePhase.audio,
        )

    def test_file_path_start(self) -> None:
        assert next_phases(FILE_PATH, None) == (PipelinePhase.audio,)

    def test_url_subtitle_fork(self) -> None:
        assert next_phases(URL_PATH, PipelinePhase.subtitle) == (
            PipelinePhase.audio,
            PipelinePhase.notegen,
        )

    def test_url_audio_and_transcribe(self) -> None:
        assert next_phases(URL_PATH, PipelinePhase.audio) == (PipelinePhase.transcribe,)
        assert next_phases(URL_PATH, PipelinePhase.transcribe) == (
            PipelinePhase.notegen,
        )

    def test_notegen_has_no_successors(self) -> None:
        assert next_phases(URL_PATH, PipelinePhase.notegen) == ()
        assert next_phases(FILE_PATH, PipelinePhase.notegen) == ()

    def test_phase_outside_path_raises(self) -> None:
        with pytest.raises(ValueError, match="not part of path"):
            next_phases(FILE_PATH, PipelinePhase.fetching)


class TestResumePoint:
    def test_no_checkpoint_starts_at_path_head(self) -> None:
        assert resume_point(URL_PATH, None) is PipelinePhase.fetching
        assert resume_point(FILE_PATH, None) is PipelinePhase.audio

    def test_resume_after_each_completed_phase_url(self) -> None:
        cases = {
            PipelinePhase.fetching: PipelinePhase.subtitle,
            PipelinePhase.audio: PipelinePhase.transcribe,
            PipelinePhase.transcribe: PipelinePhase.notegen,
        }
        for completed, expected in cases.items():
            checkpoint = Checkpoint(completed_phase=completed)
            assert resume_point(URL_PATH, checkpoint) is expected

    def test_resume_after_each_completed_phase_file(self) -> None:
        cases = {
            PipelinePhase.audio: PipelinePhase.transcribe,
            PipelinePhase.transcribe: PipelinePhase.notegen,
        }
        for completed, expected in cases.items():
            checkpoint = Checkpoint(completed_phase=completed)
            assert resume_point(FILE_PATH, checkpoint) is expected

    def test_subtitle_artifact_skips_audio_and_transcribe(self) -> None:
        checkpoint = Checkpoint(
            completed_phase=PipelinePhase.subtitle,
            artifacts=frozenset({ArtifactKind.subtitle}),
        )
        assert resume_point(URL_PATH, checkpoint) is PipelinePhase.notegen

    def test_subtitle_miss_goes_to_audio(self) -> None:
        checkpoint = Checkpoint(
            completed_phase=PipelinePhase.subtitle,
            artifacts=frozenset(),
        )
        assert resume_point(URL_PATH, checkpoint) is PipelinePhase.audio

    def test_completed_notegen_reruns_final_phase(self) -> None:
        checkpoint = Checkpoint(completed_phase=PipelinePhase.notegen)
        assert resume_point(URL_PATH, checkpoint) is PipelinePhase.notegen

    def test_subtitle_artifact_on_file_path_goes_to_notegen(self) -> None:
        # FILE_PATH has no subtitle phase, but ends at notegen, so the skip
        # target exists and resuming at notegen is safe on both paths.
        checkpoint = Checkpoint(
            completed_phase=PipelinePhase.transcribe,
            artifacts=frozenset({ArtifactKind.subtitle}),
        )
        assert resume_point(FILE_PATH, checkpoint) is PipelinePhase.notegen


class TestValidateCompletion:
    def test_notegen_completes(self) -> None:
        validate_completion(PipelinePhase.notegen)  # must not raise

    @pytest.mark.parametrize(
        "phase",
        [PipelinePhase.fetching, PipelinePhase.subtitle, PipelinePhase.audio,
         PipelinePhase.transcribe],
    )
    def test_earlier_phases_cannot_complete(self, phase: PipelinePhase) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_completion(phase)
