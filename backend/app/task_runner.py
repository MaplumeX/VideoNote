"""Single-process task registry for durable video jobs."""

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable

from app.db import increment_attempt

logger = logging.getLogger(__name__)

TaskFactory = Callable[[threading.Event], Awaitable[None]]


class TaskRunner:
    """Keep strong references to background jobs and prevent duplicate scheduling."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancel_events: dict[str, threading.Event] = {}

    def schedule(self, job_id: str, factory: TaskFactory) -> bool:
        """Schedule a task once. Returns False when the job is already running."""
        existing = self._tasks.get(job_id)
        if existing is not None and not existing.done():
            return False

        event = threading.Event()
        self._cancel_events[job_id] = event
        task = asyncio.create_task(self._run(job_id, factory, event), name=f"videonote:{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda completed, key=job_id: self._discard(key, completed))
        return True

    async def _run(self, job_id: str, factory: TaskFactory, event: threading.Event) -> None:
        if not await increment_attempt(job_id):
            return
        await factory(event)

    def _discard(self, job_id: str, completed: asyncio.Task[None]) -> None:
        self._cancel_events.pop(job_id, None)
        if self._tasks.get(job_id) is completed:
            self._tasks.pop(job_id, None)
        if not completed.cancelled() and (exc := completed.exception()) is not None:
            logger.error(
                "Unhandled background task error for %s",
                job_id,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    def cancel(self, job_id: str) -> bool:
        """Request cancellation of a currently running in-process task."""
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()
        task.cancel()
        return True

    async def cancel_and_wait(self, job_id: str) -> bool:
        """Cancel a running task and wait for its cleanup handlers."""
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def shutdown(self) -> None:
        """Cancel in-memory jobs without persisting user cancellation intent."""
        for event in self._cancel_events.values():
            event.set()
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def is_running(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        return task is not None and not task.done()


task_runner = TaskRunner()
