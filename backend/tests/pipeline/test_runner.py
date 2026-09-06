"""Tests for PipelineTaskRunner: duplicate suppression, cancel, shutdown."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app import db
from app.pipeline.orchestrator import Orchestrator
from app.pipeline.runner import PipelineTaskRunner
from app.pipeline.state import PipelinePhase, TaskStatus


async def test_schedule_runs_factory_once() -> None:
    runner = PipelineTaskRunner()
    ran: list[str] = []

    async def factory() -> None:
        ran.append("run")

    assert runner.schedule("job", factory) is True
    await asyncio.sleep(0)
    await asyncio.gather(*[t for t in runner._tasks.values()], return_exceptions=True)
    assert ran == ["run"]

async def test_schedule_suppresses_duplicates() -> None:
    runner = PipelineTaskRunner()
    started = asyncio.Event()

    async def factory() -> None:
        started.set()
        await asyncio.sleep(10)

    assert runner.schedule("job", factory) is True
    await started.wait()
    assert runner.schedule("job", factory) is False
    assert runner.is_running("job") is True
    await runner.shutdown()

async def test_cancel_and_wait_ends_task() -> None:
    runner = PipelineTaskRunner()
    cleaned: list[bool] = []

    async def factory() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cleaned.append(True)
            raise

    runner.schedule("job", factory)
    await asyncio.sleep(0)
    assert await runner.cancel_and_wait("job") is True
    assert cleaned == [True]
    assert runner.is_running("job") is False

async def test_cancel_missing_job_returns_false() -> None:
    runner = PipelineTaskRunner()
    assert runner.cancel("nope") is False
    assert await runner.cancel_and_wait("nope") is False

async def test_shutdown_cancels_without_raising() -> None:
    runner = PipelineTaskRunner()

    async def factory() -> None:
        await asyncio.sleep(10)

    runner.schedule("a", factory)
    runner.schedule("b", factory)
    await asyncio.sleep(0)
    await runner.shutdown()
    assert runner.is_running("a") is False
    assert runner.is_running("b") is False

async def test_shutdown_leaves_task_recoverable(isolated_db: Path) -> None:
    """Shutdown cancel must NOT write the cancelled terminal state: the row
    stays non-terminal so restart recovery reschedules it (durable-jobs
    contract)."""
    await db.create_task(
        "j16", user_id="user-1",
        video_url="https://www.youtube.com/watch?v=x",
        platform="youtube", language="en", source_type="url",
    )

    started = asyncio.Event()

    class _SlowFetch:
        phase = PipelinePhase.fetching
        async def run(self, ctx, *, resume):
            started.set()
            await asyncio.sleep(30)
            return type("R", (), {"outputs": {}, "extra": {}})()

    orch = Orchestrator()
    orch.stages = {}
    orch.stages[PipelinePhase.fetching] = _SlowFetch()

    from app.pipeline.runner import pipeline_runner
    assert await orch.schedule_task("j16") is True
    await started.wait()
    await pipeline_runner.shutdown()

    task = await db.get_task("j16")
    assert task["status"] == TaskStatus.running.value  # not cancelled
    assert task["cancel_requested"] == 0
    # Restart recovery picks it up again.
    assert any(t["job_id"] == "j16" for t in await db.get_recoverable_tasks())

async def test_unhandled_error_is_logged_not_raised(caplog) -> None:
    runner = PipelineTaskRunner()

    async def factory() -> None:
        raise RuntimeError("boom")

    runner.schedule("job", factory)
    await asyncio.sleep(0.1)
    assert runner.is_running("job") is False
    assert any("Unhandled pipeline task error" in r.message for r in caplog.records)

async def test_done_task_can_be_rescheduled() -> None:
    runner = PipelineTaskRunner()

    async def factory() -> None:
        return

    runner.schedule("job", factory)
    await asyncio.sleep(0.1)
    assert runner.schedule("job", factory) is True
    await runner.shutdown()
