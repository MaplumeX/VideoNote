"""Pipeline task runner: scheduling + asyncio-native cancellation (C4).

Replaces the legacy ``app/task_runner.py``. The legacy runner's cancellation
responsibility (a ``threading.Event`` threaded into every blocking service
call) is gone: stages are async, cancellation propagates via
``asyncio.Task.cancel()`` and stage-registered cancel handles (subprocess
kill). What is preserved is the durable-jobs discipline:

- ``schedule`` is duplicate-suppressing (a job is only ever running once);
- strong references to background tasks are kept (no GC of in-flight work);
- ``shutdown`` cancels in-memory jobs *without* persisting cancellation
  intent, so restart recovery can resume them.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

TaskFactory = Callable[[], Awaitable[None]]

class PipelineTaskRunner:
    """Keep strong references to pipeline jobs and prevent duplicate scheduling."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def schedule(self, job_id: str, factory: TaskFactory) -> bool:
        """Schedule a task once. Returns False when the job is already running.

        The runner is a pure in-memory task registry: it does not touch the
        database. Durable attempt-count semantics live in the orchestrator's
        scheduling entry points (recover/retry/process), where the task row is
        known to exist.
        """
        existing = self._tasks.get(job_id)
        if existing is not None and not existing.done():
            return False

        task = asyncio.create_task(factory(), name=f"pipeline:{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda completed, key=job_id: self._discard(key, completed))
        return True

    def _discard(self, job_id: str, completed: asyncio.Task[None]) -> None:
        if self._tasks.get(job_id) is completed:
            self._tasks.pop(job_id, None)
        if not completed.cancelled() and (exc := completed.exception()) is not None:
            logger.error(
                "Unhandled pipeline task error for %s",
                job_id,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    def cancel(self, job_id: str) -> bool:
        """Request cancellation of a currently running in-process task."""
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def cancel_and_wait(self, job_id: str) -> bool:
        """Cancel a running task and wait for its cleanup handlers."""
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def shutdown(self) -> None:
        """Cancel in-memory jobs without persisting user cancellation intent."""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def is_running(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        return task is not None and not task.done()

pipeline_runner = PipelineTaskRunner()
