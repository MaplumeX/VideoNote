"""Tests for the two-level progress model (app/pipeline/progress.py)."""

from app.pipeline.progress import (
    PhaseProgressTracker,
    ProgressEvent,
    ProgressPublisher,
)
from app.pipeline.state import PipelinePhase, TaskStatus


class TestProgressEvent:
    def test_fields(self) -> None:
        event = ProgressEvent(
            status=TaskStatus.running,
            phase=PipelinePhase.transcribe,
            phase_progress=0.5,
            message="Transcribing chunk 2/4",
            attempt=1,
            timestamp="2025-01-01T00:00:00+00:00",
        )
        assert event.status is TaskStatus.running
        assert event.phase is PipelinePhase.transcribe
        assert event.phase_progress == 0.5
        assert event.attempt == 1

    def test_now_stamps_utc_iso8601(self) -> None:
        event = ProgressEvent.now(
            TaskStatus.running, PipelinePhase.audio, 0.2, "Downloading", 0
        )
        assert "T" in event.timestamp
        assert event.timestamp.endswith("+00:00")

    def test_now_clamps_fraction(self) -> None:
        event = ProgressEvent.now(TaskStatus.running, PipelinePhase.audio, 1.5, "x", 0)
        assert event.phase_progress == 1.0
        event = ProgressEvent.now(TaskStatus.running, PipelinePhase.audio, -0.5, "x", 0)
        assert event.phase_progress == 0.0

    def test_phase_none_for_terminal(self) -> None:
        event = ProgressEvent.now(TaskStatus.complete, None, 1.0, "Done", 1)
        assert event.phase is None
        assert event.status is TaskStatus.complete


class _RecordingPublisher:
    """Minimal ProgressPublisher implementation for protocol conformance."""

    def __init__(self) -> None:
        self.events: list[tuple[PipelinePhase, float, str]] = []

    async def publish(self, phase: PipelinePhase, fraction: float, message: str) -> None:
        self.events.append((phase, fraction, message))


class TestProgressPublisherProtocol:
    async def test_recording_publisher_satisfies_protocol(self) -> None:
        publisher: ProgressPublisher = _RecordingPublisher()
        await publisher.publish(PipelinePhase.audio, 0.5, "halfway")
        assert isinstance(publisher, ProgressPublisher)


class TestPhaseProgressTracker:
    def test_clamps_to_unit_interval(self) -> None:
        tracker = PhaseProgressTracker()
        assert tracker.update(PipelinePhase.audio, -0.3) == 0.0
        assert tracker.update(PipelinePhase.audio, 2.0) == 1.0

    def test_monotonic_within_phase(self) -> None:
        tracker = PhaseProgressTracker()
        assert tracker.update(PipelinePhase.transcribe, 0.2) == 0.2
        assert tracker.update(PipelinePhase.transcribe, 0.5) == 0.5
        # regression clamped to running max
        assert tracker.update(PipelinePhase.transcribe, 0.1) == 0.5
        # equal value is fine
        assert tracker.update(PipelinePhase.transcribe, 0.5) == 0.5

    def test_phase_switch_resets(self) -> None:
        tracker = PhaseProgressTracker()
        tracker.update(PipelinePhase.transcribe, 0.9)
        # switching phase starts fresh — a lower fraction is accepted
        assert tracker.update(PipelinePhase.notegen, 0.1) == 0.1

    def test_regression_after_reset_rejected_again(self) -> None:
        tracker = PhaseProgressTracker()
        tracker.update(PipelinePhase.audio, 0.8)
        tracker.update(PipelinePhase.transcribe, 0.3)
        assert tracker.update(PipelinePhase.transcribe, 0.2) == 0.3
        assert tracker.update(PipelinePhase.audio, 0.1) == 0.1

    def test_tracks_current_phase(self) -> None:
        tracker = PhaseProgressTracker()
        assert tracker.phase is None
        tracker.update(PipelinePhase.fetching, 0.0)
        assert tracker.phase is PipelinePhase.fetching
        assert tracker.max_fraction == 0.0

    def test_clamping_applies_before_monotonic_check(self) -> None:
        tracker = PhaseProgressTracker()
        assert tracker.update(PipelinePhase.audio, 0.4) == 0.4
        # 5.0 clamps to 1.0, which is still >= 0.4
        assert tracker.update(PipelinePhase.audio, 5.0) == 1.0
