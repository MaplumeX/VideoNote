"""Orchestrator integration tests (C4): fake stages, real SQLite, zero network.

Covers the three execution paths end to end, the subtitle-hit skip, error and
cancellation terminal states, checkpoint advancement, terminal-write
idempotency, retry-from-checkpoint (no re-run of completed phases), and
cross-stage extra propagation (audio_path -> transcribe, notes -> result_json).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app import db
from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.orchestrator import Orchestrator
from app.pipeline.state import (
    URL_PATH,
    ArtifactKind,
    PipelinePhase,
    TaskStatus,
)
from tests.pipeline.conftest import fake_stage, make_plan


@pytest.fixture
def orch() -> Orchestrator:
    o = Orchestrator()
    o.stages = {}
    return o

async def _create_task(job_id: str, **kwargs) -> None:
    await db.create_task(job_id, user_id="user-1", **kwargs)

# --- Three execution paths ---------------------------------------------------

async def test_url_path_with_subtitles_end_to_end(
    isolated_db: Path, orch: Orchestrator
) -> None:
    await _create_task("j1", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    calls: list[PipelinePhase] = []
    stages = {
        PipelinePhase.fetching: fake_stage(
            PipelinePhase.fetching,
            outputs={ArtifactKind.video_meta: {"title": "T", "thumbnail": None}},
            on_run=lambda ctx, r: calls.append(PipelinePhase.fetching),
        ),
        PipelinePhase.subtitle: fake_stage(
            PipelinePhase.subtitle,
            outputs={ArtifactKind.subtitle: "subs"},
            on_run=lambda ctx, r: calls.append(PipelinePhase.subtitle),
        ),
        PipelinePhase.audio: fake_stage(
            PipelinePhase.audio, on_run=lambda ctx, r: calls.append(PipelinePhase.audio)
        ),
        PipelinePhase.transcribe: fake_stage(
            PipelinePhase.transcribe,
            outputs={ArtifactKind.transcript: "tr"},
            extra={"audio_path": "/tmp/x.wav"},
            on_run=lambda ctx, r: calls.append(PipelinePhase.transcribe),
        ),
        PipelinePhase.notegen: fake_stage(
            PipelinePhase.notegen,
            extra={"notes": "# Notes"},
            on_run=lambda ctx, r: calls.append(PipelinePhase.notegen),
        ),
    }
    orch.stages.update(stages)

    await orch.run(make_plan("j1"))

    # Subtitle hit skips audio + transcribe.
    assert calls == [
        PipelinePhase.fetching,
        PipelinePhase.subtitle,
        PipelinePhase.notegen,
    ]
    task = await db.get_task("j1")
    assert task["status"] == TaskStatus.complete.value
    assert task["phase"] is None
    assert json.loads(task["result_json"])["markdown"] == "# Notes"
    assert json.loads(task["result_json"])["title"] == "T"
    assert task["title"] == "T"
    # Artifacts persisted.
    assert await db.get_artifact("j1", "video_meta") == {"title": "T", "thumbnail": None}
    assert await db.get_artifact("j1", "subtitle") == "subs"

async def test_url_path_without_subtitles_runs_asr(
    isolated_db: Path, orch: Orchestrator
) -> None:
    await _create_task("j2", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    calls: list[PipelinePhase] = []

    def rec(phase):
        return lambda ctx, r: calls.append(phase)

    transcribe_extra: dict[str, object] = {}

    class _Transcribe:
        phase = PipelinePhase.transcribe
        async def run(self, ctx, *, resume):
            calls.append(PipelinePhase.transcribe)
            transcribe_extra.update(ctx.extra)
            return type("R", (), {"outputs": {ArtifactKind.transcript: "tr"},
                                  "extra": {}})()

    orch.stages.update({
        PipelinePhase.fetching: fake_stage(
            PipelinePhase.fetching,
            outputs={ArtifactKind.video_meta: {"title": None, "thumbnail": None}},
            on_run=rec(PipelinePhase.fetching)),
        PipelinePhase.subtitle: fake_stage(
            PipelinePhase.subtitle, outputs={}, on_run=rec(PipelinePhase.subtitle)),
        PipelinePhase.audio: fake_stage(
            PipelinePhase.audio, extra={"audio_path": "/tmp/j2.wav"},
            on_run=rec(PipelinePhase.audio)),
        PipelinePhase.transcribe: _Transcribe(),
        PipelinePhase.notegen: fake_stage(
            PipelinePhase.notegen, extra={"notes": "N"}, on_run=rec(PipelinePhase.notegen)),
    })

    await orch.run(make_plan("j2"))

    assert calls == [
        PipelinePhase.fetching, PipelinePhase.subtitle,
        PipelinePhase.audio, PipelinePhase.transcribe, PipelinePhase.notegen,
    ]
    # audio_path extra propagated into the transcribe context.
    assert transcribe_extra["audio_path"] == "/tmp/j2.wav"
    task = await db.get_task("j2")
    assert task["status"] == TaskStatus.complete.value

async def test_upload_file_path_end_to_end(isolated_db: Path, orch: Orchestrator) -> None:
    upload = isolated_db / "j3_input.mp4"
    upload.write_bytes(b"video")
    await _create_task("j3", source_type="upload", language="en",
                       file_name="input.mp4", input_file_path=str(upload))
    calls: list[PipelinePhase] = []

    def rec(phase):
        return lambda ctx, r: calls.append(phase)

    orch.stages.update({
        PipelinePhase.audio: fake_stage(
            PipelinePhase.audio, extra={"audio_path": "/tmp/j3.wav"},
            on_run=rec(PipelinePhase.audio)),
        PipelinePhase.transcribe: fake_stage(
            PipelinePhase.transcribe, outputs={ArtifactKind.transcript: "tr"},
            on_run=rec(PipelinePhase.transcribe)),
        PipelinePhase.notegen: fake_stage(
            PipelinePhase.notegen, extra={"notes": "N"}, on_run=rec(PipelinePhase.notegen)),
    })

    await orch.run(make_plan("j3", source_type="upload", input_path=str(upload)))

    assert calls == [PipelinePhase.audio, PipelinePhase.transcribe, PipelinePhase.notegen]
    task = await db.get_task("j3")
    assert task["status"] == TaskStatus.complete.value
    # Upload input cleaned at completion.
    assert not upload.exists()
    assert task["input_file_path"] is None

# --- Failure / cancellation ---------------------------------------------------

async def test_pipeline_error_writes_failed(isolated_db: Path, orch: Orchestrator) -> None:
    await _create_task("j4", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    orch.stages[PipelinePhase.fetching] = fake_stage(
        PipelinePhase.fetching,
        error=PipelineError(ErrorCode.VIDEO_PRIVATE, detail="login required"),
    )
    await orch.run(make_plan("j4"))
    task = await db.get_task("j4")
    assert task["status"] == TaskStatus.failed.value
    assert task["last_error_code"] == "VIDEO_PRIVATE"
    assert task["message"] == "VIDEO_PRIVATE: login required"

async def test_unexpected_error_maps_to_processing_failed(
    isolated_db: Path, orch: Orchestrator
) -> None:
    await _create_task("j5", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    orch.stages[PipelinePhase.fetching] = fake_stage(
        PipelinePhase.fetching, error=RuntimeError("boom sk-abcdef12345678")
    )
    await orch.run(make_plan("j5"))
    task = await db.get_task("j5")
    assert task["status"] == TaskStatus.failed.value
    assert task["last_error_code"] == "PROCESSING_FAILED"
    # Detail sanitized: no raw API key fragment.
    assert "sk-abcdef" not in task["message"]

async def test_cancelled_error_with_durable_intent_writes_cancelled(
    isolated_db: Path, orch: Orchestrator
) -> None:
    """A CancelledError with a persisted cancel intent converges to cancelled."""
    await _create_task("j6", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")

    class _Cancellable:
        phase = PipelinePhase.fetching
        async def run(self, ctx, *, resume):
            # Mirrors the production path: the route persists the durable
            # intent (request_task_cancel) before runner.cancel() delivers
            # the asyncio cancellation into the stage await.
            await db.request_task_cancel("j6", user_id="user-1")
            raise asyncio.CancelledError()

    orch.stages[PipelinePhase.fetching] = _Cancellable()
    with pytest.raises(asyncio.CancelledError):
        await orch.run(make_plan("j6"))
    task = await db.get_task("j6")
    assert task["status"] == TaskStatus.cancelled.value
    assert task["last_error_code"] == "TASK_CANCELLED"

async def test_cancelled_error_without_intent_stays_recoverable(
    isolated_db: Path, orch: Orchestrator
) -> None:
    """A CancelledError with no durable intent is a shutdown interruption.

    The task must stay non-terminal (running) so restart recovery resumes
    it — the durable-jobs contract: shutdown preserves recoverable state.
    """
    await _create_task("j6b", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")

    class _ShutdownLike:
        phase = PipelinePhase.fetching
        async def run(self, ctx, *, resume):
            raise asyncio.CancelledError()

    orch.stages[PipelinePhase.fetching] = _ShutdownLike()
    with pytest.raises(asyncio.CancelledError):
        await orch.run(make_plan("j6b"))
    task = await db.get_task("j6b")
    assert task["status"] == TaskStatus.running.value
    assert task["cancel_requested"] == 0

async def test_persisted_cancel_intent_between_phases(
    isolated_db: Path, orch: Orchestrator
) -> None:
    """A cancel request landing between phases converges to cancelled."""
    await _create_task("j7", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")

    class _AfterFirstPhase:
        phase = PipelinePhase.fetching
        async def run(self, ctx, *, resume):
            # User cancels while the loop is between phases.
            await db.request_task_cancel("j7", user_id="user-1")
            return type("R", (), {"outputs": {ArtifactKind.video_meta: {}}, "extra": {}})()

    orch.stages[PipelinePhase.fetching] = _AfterFirstPhase()
    orch.stages[PipelinePhase.subtitle] = fake_stage(PipelinePhase.subtitle)
    await orch.run(make_plan("j7"))
    task = await db.get_task("j7")
    assert task["status"] == TaskStatus.cancelled.value
    # The subtitle stage never ran.
    assert orch.stages[PipelinePhase.subtitle].calls == []  # type: ignore[attr-defined]

# --- Checkpoint / resume / retry ----------------------------------------------

async def test_retry_resumes_from_checkpoint_no_transcribe_rerun(
    isolated_db: Path, orch: Orchestrator
) -> None:
    """R2 acceptance: LLM failure -> retry does not re-run transcription."""
    await _create_task("j8", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    asr_calls: list[bool] = []

    orch.stages.update({
        PipelinePhase.fetching: fake_stage(
            PipelinePhase.fetching,
            outputs={ArtifactKind.video_meta: {"title": None, "thumbnail": None}}),
        PipelinePhase.subtitle: fake_stage(PipelinePhase.subtitle, outputs={}),
        PipelinePhase.audio: fake_stage(
            PipelinePhase.audio, extra={"audio_path": "/tmp/j8.wav"}),
        PipelinePhase.transcribe: fake_stage(
            PipelinePhase.transcribe,
            outputs={ArtifactKind.transcript: "tr"},
            on_run=lambda ctx, r: asr_calls.append(True)),
        PipelinePhase.notegen: fake_stage(PipelinePhase.notegen),
    })
    # First run: notegen fails.
    orch.stages[PipelinePhase.notegen] = fake_stage(
        PipelinePhase.notegen, error=PipelineError(ErrorCode.NOTE_GENERATION_FAILED))
    await orch.run(make_plan("j8"))
    task = await db.get_task("j8")
    assert task["status"] == TaskStatus.failed.value
    assert len(asr_calls) == 1

    # Retry: notegen succeeds; transcript artifact is already persisted so the
    # transcribe phase is skipped entirely by the resume point.
    orch.stages[PipelinePhase.notegen] = fake_stage(
        PipelinePhase.notegen, extra={"notes": "recovered"})
    assert await orch.retry("j8") is True
    from app.pipeline.runner import pipeline_runner
    await asyncio.gather(*pipeline_runner._tasks.values(), return_exceptions=True)

    task = await db.get_task("j8")
    assert task["status"] == TaskStatus.complete.value
    assert json.loads(task["result_json"])["markdown"] == "recovered"
    # No second ASR call.
    assert len(asr_calls) == 1

async def test_retry_only_failed_or_cancelled(isolated_db: Path) -> None:
    await _create_task("j9", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    # pending (never run) is not retryable via reset_task_for_retry
    orch = Orchestrator()
    assert await orch.retry("j9") is False

async def test_attempt_limit_blocks_recovery(isolated_db: Path) -> None:
    await _create_task("j10", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    conn = await db._get_db()
    await conn.execute(
        "UPDATE tasks SET attempt_count = ? WHERE job_id = ?", (db.MAX_TASK_ATTEMPTS, "j10")
    )
    await conn.commit()
    orch = Orchestrator()
    await orch.recover()
    task = await db.get_task("j10")
    assert task["status"] == TaskStatus.failed.value
    assert task["last_error_code"] == "TASK_RECOVERY_MAX_ATTEMPTS"

# --- Terminal write idempotency ------------------------------------------------

async def test_terminal_write_is_idempotent(isolated_db: Path) -> None:
    await _create_task("j11", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    await db.set_task_terminal(
        "j11", TaskStatus.failed.value, message="X", last_error_code="PROCESSING_FAILED"
    )
    # Second terminal write with a different status must not overwrite.
    ok = await db.set_task_terminal("j11", TaskStatus.complete.value, message="Done")
    assert ok is False
    task = await db.get_task("j11")
    assert task["status"] == TaskStatus.failed.value

# --- Progress publisher monotonicity -------------------------------------------

async def test_progress_publisher_monotonic_within_phase(
    isolated_db: Path
) -> None:
    from app.pipeline.context import _ProgressPublisher
    from app.pipeline.state import PipelinePhase

    await _create_task("j12", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    pub = _ProgressPublisher("j12")
    await pub.publish(PipelinePhase.transcribe, 0.5, "half")
    await pub.publish(PipelinePhase.transcribe, 0.2, "regression")  # clamped
    task = await db.get_task("j12")
    assert task["phase_progress"] == 0.5
    assert task["phase"] == "transcribe"

# --- Per-user cookiefile injection --------------------------------------------

async def test_cookiefile_injected_into_url_stage_contexts(
    isolated_db: Path, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user with a per-platform cookie gets a temp cookiefile path in
    StageContext.extra ("cookiefile") for every yt-dlp stage of the run;
    the temp file is removed after the run."""
    from app.crypto import encrypt_api_key

    await db.create_user("user-1", "u1@example.com", "hash")
    await _create_task("j16", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    await db.save_user_cookie("user-1", "youtube", encrypt_api_key("# Netscape cookies"))

    import app.pipeline.orchestrator as orch_module

    seen: list[str | None] = []
    real_orch_method = Orchestrator._write_cookiefile

    async def spy_method(self, job_id, url):
        path = await real_orch_method(self, job_id, url)
        if path:
            seen.append(path)
        return path

    monkeypatch.setattr(orch_module.Orchestrator, "_write_cookiefile", spy_method)

    extras: list[dict] = []

    def rec(phase):
        def on_run(ctx, resume):
            extras.append(dict(ctx.extra))
        return on_run

    orch.stages.update({
        PipelinePhase.fetching: fake_stage(
            PipelinePhase.fetching,
            outputs={ArtifactKind.video_meta: {"title": None, "thumbnail": None}},
            on_run=rec(PipelinePhase.fetching)),
        PipelinePhase.subtitle: fake_stage(
            PipelinePhase.subtitle, outputs={}, on_run=rec(PipelinePhase.subtitle)),
        PipelinePhase.audio: fake_stage(
            PipelinePhase.audio, extra={"audio_path": "/tmp/j16.wav"},
            on_run=rec(PipelinePhase.audio)),
        PipelinePhase.transcribe: fake_stage(
            PipelinePhase.transcribe, outputs={ArtifactKind.transcript: "tr"}),
        PipelinePhase.notegen: fake_stage(
            PipelinePhase.notegen, extra={"notes": "N"}),
    })

    await orch.run(make_plan("j16"))

    task = await db.get_task("j16")
    assert task["status"] == TaskStatus.complete.value
    # The cookiefile was materialized once and injected into every
    # pre-notegen stage context (fetch/subtitle/audio).
    assert len(seen) == 1
    cookiefile = seen[0]
    for phase_extras in extras:
        assert phase_extras["cookiefile"] == cookiefile
    # Temp cookie file cleaned up after the run.
    from pathlib import Path as _Path
    assert not _Path(cookiefile).exists()

async def test_no_cookie_extra_without_user_cookie(
    isolated_db: Path, orch: Orchestrator
) -> None:
    """No cookiefile key in extra when the user has no per-platform cookie."""
    await _create_task("j17", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    extras: list[dict] = []

    orch.stages.update({
        PipelinePhase.fetching: fake_stage(
            PipelinePhase.fetching,
            outputs={ArtifactKind.video_meta: {"title": None, "thumbnail": None}},
            on_run=lambda ctx, r: extras.append(dict(ctx.extra)),
        ),
        PipelinePhase.subtitle: fake_stage(PipelinePhase.subtitle, outputs={}),
        PipelinePhase.audio: fake_stage(
            PipelinePhase.audio, extra={"audio_path": "/tmp/j17.wav"}),
        PipelinePhase.transcribe: fake_stage(
            PipelinePhase.transcribe, outputs={ArtifactKind.transcript: "tr"}),
        PipelinePhase.notegen: fake_stage(
            PipelinePhase.notegen, extra={"notes": "N"}),
    })

    await orch.run(make_plan("j17"))

    # The fetching stage saw no cookiefile key (user has no cookie).
    assert all("cookiefile" not in e for e in extras)
    task = await db.get_task("j17")
    assert task["status"] == TaskStatus.complete.value

# --- advance() unit checks ------------------------------------------------------

def test_advance_subtitle_hit_skips_to_notegen() -> None:
    from app.pipeline.context import advance
    assert advance(
        URL_PATH, PipelinePhase.subtitle, artifact_kinds=frozenset({ArtifactKind.subtitle})
    ) is PipelinePhase.notegen

def test_advance_subtitle_miss_goes_to_audio() -> None:
    from app.pipeline.context import advance
    assert advance(
        URL_PATH, PipelinePhase.subtitle, artifact_kinds=frozenset()
    ) is PipelinePhase.audio

def test_advance_notegen_completes() -> None:
    from app.pipeline.context import advance
    assert advance(URL_PATH, PipelinePhase.notegen, artifact_kinds=frozenset()) is None

# --- Resume fixes (regression) ---------------------------------------------

async def test_retry_after_subtitle_hit_skips_audio_and_transcribe(
    isolated_db: Path, orch: Orchestrator
) -> None:
    """Subtitle-hit resume rule: a persisted subtitle artifact must resume at
    notegen, not re-run audio + transcribe (the checkpoint row alone carries
    no artifact set — the store must be consulted)."""
    await _create_task("j13", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    await db.save_artifact("j13", ArtifactKind.video_meta.value, {"title": "T", "thumbnail": None})
    await db.save_artifact("j13", ArtifactKind.subtitle.value, "SUBS")
    assert await db.save_checkpoint(
        "j13", PipelinePhase.subtitle.value,
        status=TaskStatus.running.value, phase=PipelinePhase.subtitle.value,
    )
    await db.set_task_terminal(
        "j13", TaskStatus.failed.value,
        message="NOTE_GENERATION_FAILED",
        last_error_code="NOTE_GENERATION_FAILED",
    )

    ran: list[PipelinePhase] = []

    def _forbidden(phase: PipelinePhase):
        class _No:
            phase_attr = phase
            async def run(self, ctx, *, resume):
                ran.append(phase)
                raise AssertionError(f"{phase} must not re-run on subtitle-hit resume")
        return _No()

    for ph in (PipelinePhase.fetching, PipelinePhase.subtitle,
               PipelinePhase.audio, PipelinePhase.transcribe):
        orch.stages[ph] = _forbidden(ph)
    orch.stages[PipelinePhase.notegen] = fake_stage(
        PipelinePhase.notegen, extra={"notes": "N"}
    )

    assert await orch.retry("j13") is True
    from app.pipeline.runner import pipeline_runner
    await asyncio.gather(*pipeline_runner._tasks.values(), return_exceptions=True)

    task = await db.get_task("j13")
    assert task["status"] == TaskStatus.complete.value
    assert json.loads(task["result_json"])["markdown"] == "N"
    assert ran == []

async def test_resume_past_audio_restores_audio_path(
    isolated_db: Path, orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A checkpoint resume at transcribe must have audio_path in ctx.extra
    (the per-job WAV), so the transcribe stage does not fail with
    PROCESSING_FAILED."""
    from app.pipeline.context import wav_path_for

    await _create_task("j14", video_url="https://www.youtube.com/watch?v=x",
                       platform="youtube", language="en", source_type="url")
    # Audio completed (checkpoint=audio), crash before transcribe: the resume
    # point is transcribe, which needs audio_path from the per-job WAV.
    assert await db.save_checkpoint(
        "j14", PipelinePhase.audio.value,
        status=TaskStatus.running.value, phase=PipelinePhase.transcribe.value,
    )
    await db.set_task_terminal(
        "j14", TaskStatus.failed.value,
        message="TRANSCRIPTION_FAILED",
        last_error_code="TRANSCRIPTION_FAILED",
    )

    # Simulate the C2-contract per-job WAV still on disk.
    wav = wav_path_for("j14")
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF....")

    seen: dict[str, object] = {}

    class _Transcribe:
        phase = PipelinePhase.transcribe
        async def run(self, ctx, *, resume):
            seen["audio_path"] = ctx.extra.get("audio_path")
            return type("R", (), {"outputs": {}, "extra": {}})()

    class _Notegen:
        phase = PipelinePhase.notegen
        async def run(self, ctx, *, resume):
            return type("R", (), {"outputs": {}, "extra": {"notes": "N"}})()

    orch.stages[PipelinePhase.transcribe] = _Transcribe()
    orch.stages[PipelinePhase.notegen] = _Notegen()

    assert await orch.retry("j14") is True
    from app.pipeline.runner import pipeline_runner
    await asyncio.gather(*pipeline_runner._tasks.values(), return_exceptions=True)

    task = await db.get_task("j14")
    assert task["status"] == TaskStatus.complete.value
    assert seen.get("audio_path") == str(wav)

    wav.unlink(missing_ok=True)

async def test_resume_past_audio_without_wav_rewinds_to_audio(
    isolated_db: Path, orch: Orchestrator
) -> None:
    """When the per-job WAV is gone, the audio phase re-runs (checkpoint
    rewound) instead of failing transcribe with a missing audio_path."""
    from app.pipeline.context import wav_path_for

    up = isolated_db / "j15_input.mp4"
    up.write_bytes(b"video")
    await _create_task("j15", source_type="upload", language="en",
                       file_name="input.mp4", input_file_path=str(up))
    assert await db.save_checkpoint(
        "j15", PipelinePhase.audio.value,
        status=TaskStatus.running.value, phase=PipelinePhase.transcribe.value,
    )
    await db.set_task_terminal(
        "j15", TaskStatus.failed.value,
        message="NOTE_GENERATION_FAILED",
        last_error_code="NOTE_GENERATION_FAILED",
    )
    wav_path_for("j15").unlink(missing_ok=True)

    calls: list[PipelinePhase] = []

    def rec(phase: PipelinePhase):
        async def run(ctx, *, resume):
            calls.append(phase)
            if phase is PipelinePhase.audio:
                return type("R", (), {"outputs": {}, "extra": {"audio_path": "/tmp/j15.wav"}})()
            if phase is PipelinePhase.transcribe:
                return type("R", (), {"outputs": {ArtifactKind.transcript: "tr"}, "extra": {}})()
            return type("R", (), {"outputs": {}, "extra": {"notes": "N"}})()
        return run

    for ph in (PipelinePhase.audio, PipelinePhase.transcribe, PipelinePhase.notegen):
        orch.stages[ph] = type(f"S{ph.value}", (), {"phase": ph, "run": staticmethod(rec(ph))})()

    assert await orch.retry("j15") is True
    from app.pipeline.runner import pipeline_runner
    await asyncio.gather(*pipeline_runner._tasks.values(), return_exceptions=True)

    task = await db.get_task("j15")
    assert task["status"] == TaskStatus.complete.value
    assert calls == [PipelinePhase.audio, PipelinePhase.transcribe, PipelinePhase.notegen]
