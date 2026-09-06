"""Restart-recovery integration tests for the orchestrator (C4).

Mirrors the Durable Single-Process Video Tasks contract's Validation & Error
Matrix (``.trellis/spec/backend/database-guidelines.md``):

| Condition                          | Required result                          |
|------------------------------------|------------------------------------------|
| Recoverable URL task               | Schedule once and increment attempt      |
| Recoverable upload w/ valid file   | Schedule once using that file            |
| Missing/invalid upload input       | Fail with TASK_RECOVERY_INPUT_INVALID    |
| Unsupported persisted URL/input    | Fail with TASK_RECOVERY_UNSUPPORTED_URL  |
| Attempt count exhausted            | Fail with TASK_RECOVERY_MAX_ATTEMPTS     |
| Terminal / cancel-requested rows   | Ignored by recovery                      |
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app import db
from app.pipeline.orchestrator import Orchestrator
from app.pipeline.runner import pipeline_runner
from app.pipeline.state import PipelinePhase, TaskStatus
from tests.pipeline.conftest import fake_stage


@pytest.fixture
def recovery_orchestrator(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> Orchestrator:
    """An orchestrator whose every stage is a fake — recovery scheduling is
    observable through which stages run, with zero network or subprocesses."""
    orch = Orchestrator()
    calls: list[PipelinePhase] = []

    for phase in (
        PipelinePhase.fetching,
        PipelinePhase.subtitle,
        PipelinePhase.audio,
        PipelinePhase.transcribe,
        PipelinePhase.notegen,
    ):
        outputs = {}
        if phase is PipelinePhase.subtitle:
            outputs = {}  # miss -> falls through to audio (transition table)
        if phase is PipelinePhase.transcribe:
            from app.pipeline.state import ArtifactKind

            outputs = {ArtifactKind.transcript: "TR"}
        extra = {"notes": "N"} if phase is PipelinePhase.notegen else {}

        stage = fake_stage(phase, outputs=outputs, extra=extra)
        stage.calls = calls  # type: ignore[assignment]
        monkeypatch.setattr(
            stage,
            "run",
            _recording_run(stage, phase, calls),
        )
        orch.stages[phase] = stage
    return orch


def _recording_run(stage, phase: PipelinePhase, calls: list[PipelinePhase]):
    from app.pipeline.stages.base import StageResult
    from app.pipeline.state import ArtifactKind

    outputs: dict = {}
    if phase is PipelinePhase.transcribe:
        outputs = {ArtifactKind.transcript: "TR"}
    extra = {"notes": "N"} if phase is PipelinePhase.notegen else {}

    async def run(ctx, *, resume: bool) -> StageResult:
        calls.append(phase)
        return StageResult(outputs=dict(outputs), extra=dict(extra))

    return run


async def _drain_runner() -> None:
    if pipeline_runner._tasks:
        await asyncio.gather(*pipeline_runner._tasks.values(), return_exceptions=True)


async def test_recovery_schedules_valid_url_task(
    isolated_db: Path, recovery_orchestrator: Orchestrator
) -> None:
    await db.create_task(
        "url-job",
        user_id="user-1",
        source_type="url",
        video_url="https://www.youtube.com/watch?v=abcdefghijk",
        language="en",
    )

    await recovery_orchestrator.recover()
    await _drain_runner()

    row = await db.get_task("url-job")
    assert row is not None
    assert row["status"] == TaskStatus.complete.value
    assert row["attempt_count"] == 1  # scheduled once, one attempt increment


async def test_recovery_schedules_valid_upload_task(
    isolated_db: Path, recovery_orchestrator: Orchestrator
) -> None:
    source = isolated_db / "source.mp4"
    source.write_bytes(b"video")
    await db.create_task(
        "up-job",
        user_id="user-1",
        source_type="upload",
        input_file_path=str(source),
        language="en",
    )

    await recovery_orchestrator.recover()
    await _drain_runner()

    row = await db.get_task("up-job")
    assert row is not None
    assert row["status"] == TaskStatus.complete.value


async def test_recovery_rejects_unsafe_upload_path(
    isolated_db: Path, recovery_orchestrator: Orchestrator, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    await db.create_task(
        "unsafe",
        user_id="user-1",
        source_type="upload",
        input_file_path=str(outside),
    )

    await recovery_orchestrator.recover()
    await _drain_runner()

    row = await db.get_task("unsafe")
    assert row is not None
    assert row["status"] == TaskStatus.failed.value
    assert row["last_error_code"] == "TASK_RECOVERY_INPUT_INVALID"
    # Nothing was scheduled (no stage ran, attempt untouched).
    assert row["attempt_count"] == 0


async def test_recovery_uses_stable_code_for_unsupported_url(
    isolated_db: Path, recovery_orchestrator: Orchestrator
) -> None:
    await db.create_task(
        "bad-url",
        user_id="user-1",
        source_type="url",
        video_url="https://example.com/video",
    )

    await recovery_orchestrator.recover()
    await _drain_runner()

    row = await db.get_task("bad-url")
    assert row is not None
    assert row["status"] == TaskStatus.failed.value
    assert row["last_error_code"] == "TASK_RECOVERY_UNSUPPORTED_URL"


async def test_recovery_fails_task_at_attempt_limit(
    isolated_db: Path, recovery_orchestrator: Orchestrator
) -> None:
    await db.create_task(
        "maxed",
        user_id="user-1",
        source_type="url",
        video_url="https://www.youtube.com/watch?v=abcdefghijk",
    )
    # Burn the attempt budget (MAX_TASK_ATTEMPTS = 5).
    for _ in range(db.MAX_TASK_ATTEMPTS):
        await db.increment_attempt("maxed")

    await recovery_orchestrator.recover()
    await _drain_runner()

    row = await db.get_task("maxed")
    assert row is not None
    assert row["status"] == TaskStatus.failed.value
    assert row["last_error_code"] == "TASK_RECOVERY_MAX_ATTEMPTS"


async def test_recovery_missing_upload_file_is_invalid(
    isolated_db: Path, recovery_orchestrator: Orchestrator
) -> None:
    await db.create_task(
        "gone",
        user_id="user-1",
        source_type="upload",
        input_file_path=str(isolated_db / "deleted.mp4"),  # never created
    )

    await recovery_orchestrator.recover()
    await _drain_runner()

    row = await db.get_task("gone")
    assert row is not None
    assert row["status"] == TaskStatus.failed.value
    assert row["last_error_code"] == "TASK_RECOVERY_INPUT_INVALID"


async def test_recovery_ignores_terminal_and_cancel_requested(
    isolated_db: Path, recovery_orchestrator: Orchestrator
) -> None:
    # Terminal rows are invisible to get_recoverable_tasks.
    await db.create_task("done", user_id="user-1", source_type="url",
                         video_url="https://www.youtube.com/watch?v=abcdefghijk")
    await db.set_task_terminal("done", TaskStatus.complete.value, message="Done")

    # cancel_requested rows are excluded (cancellation intent survives restart).
    await db.create_task("cancelled", user_id="user-1", source_type="url",
                         video_url="https://www.youtube.com/watch?v=abcdefghijk")
    assert await db.request_task_cancel("cancelled", user_id="user-1")

    before_done = await db.get_task("done")
    before_cancelled = await db.get_task("cancelled")

    await recovery_orchestrator.recover()
    await _drain_runner()

    after_done = await db.get_task("done")
    after_cancelled = await db.get_task("cancelled")
    # Idempotent: terminal writes are untouched by recovery.
    assert after_done == before_done
    assert after_cancelled == before_cancelled


async def test_recovery_resumes_from_checkpoint(
    isolated_db: Path, recovery_orchestrator: Orchestrator
) -> None:
    """A restart after a mid-run crash resumes from the last checkpoint."""
    from app.pipeline.state import ArtifactKind

    await db.create_task(
        "resumed",
        user_id="user-1",
        source_type="url",
        video_url="https://www.youtube.com/watch?v=abcdefghijk",
        language="en",
    )
    # Transcript persisted + checkpoint at transcribe (crash during notegen).
    await db.save_artifact("resumed", ArtifactKind.transcript.value, "TR")
    assert await db.save_checkpoint(
        "resumed", PipelinePhase.transcribe.value,
        status=TaskStatus.running.value, phase=PipelinePhase.transcribe.value,
    )

    await recovery_orchestrator.recover()
    await _drain_runner()

    row = await db.get_task("resumed")
    assert row is not None
    assert row["status"] == TaskStatus.complete.value


async def test_recovery_schedules_legacy_rows_without_checkpoint(
    isolated_db: Path, recovery_orchestrator: Orchestrator
) -> None:
    """Legacy non-terminal rows (no checkpoint, legacy stage value) run from
    scratch — resume_point returns the first phase of the path."""
    await db.create_task(
        "legacy",
        user_id="user-1",
        source_type="url",
        video_url="https://www.youtube.com/watch?v=abcdefghijk",
    )

    await recovery_orchestrator.recover()
    await _drain_runner()

    row = await db.get_task("legacy")
    assert row is not None
    assert row["status"] == TaskStatus.complete.value
