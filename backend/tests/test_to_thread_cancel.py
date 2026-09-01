import asyncio
import threading

import pytest

from app.api.routes import _to_thread_with_cancel


async def test_slow_call_executes_exactly_once() -> None:
    calls = 0

    def blocking() -> str:
        nonlocal calls
        calls += 1
        await_time = 0.5
        event = threading.Event()
        threading.Timer(await_time, event.set).start()
        while not event.is_set():
            pass
        return "done"

    result = await _to_thread_with_cancel(blocking, timeout=0.05)
    assert result == "done"
    assert calls == 1


async def test_cancel_event_raises_cancelled_error() -> None:
    event = threading.Event()
    started = threading.Event()

    def blocking() -> None:
        started.set()
        event2 = threading.Event()
        threading.Timer(5.0, event2.set).start()
        while not event2.is_set():
            pass

    async def cancel_soon() -> None:
        while not started.is_set():
            await asyncio.sleep(0.01)
        event.set()

    cancel_task = asyncio.create_task(cancel_soon())
    with pytest.raises(asyncio.CancelledError):
        await _to_thread_with_cancel(blocking, cancel_event=event, timeout=0.05)
    await cancel_task


async def test_exception_propagates() -> None:
    def failing() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await _to_thread_with_cancel(failing, timeout=0.05)


async def test_cancel_event_none_still_completes() -> None:
    def blocking() -> int:
        return 42

    result = await _to_thread_with_cancel(blocking, timeout=0.05)
    assert result == 42


async def test_slow_call_with_event_completes_without_cancellation() -> None:
    event = threading.Event()

    def blocking() -> str:
        event3 = threading.Event()
        threading.Timer(0.2, event3.set).start()
        while not event3.is_set():
            pass
        return "ok"

    result = await _to_thread_with_cancel(blocking, cancel_event=event, timeout=0.05)
    assert result == "ok"
