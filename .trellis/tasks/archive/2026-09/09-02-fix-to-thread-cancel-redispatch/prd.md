# PRD: Fix duplicate yt-dlp downloads caused by `_to_thread_with_cancel` re-dispatch loop

## Background

User reports Bilibili video processing fails after uploading cookies. Log analysis
shows the audio download itself succeeds (reaches 100%), but three concurrent
yt-dlp download threads (Task-1672/1673/1674) write the same
`/tmp/.../audio.m4a.part` file simultaneously, producing:

- `FileNotFoundError: audio.f100026.m4a` / rename failures
- `HTTP Error 403: Forbidden` (Bilibili rejecting concurrent fragment requests)
- `Task exception was never retrieved` warnings from discarded futures

## Root Cause

`backend/app/api/routes.py` — `_to_thread_with_cancel()`:

```python
while True:
    fut = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))  # inside loop
    done, _ = await asyncio.wait({fut}, timeout=timeout)
    if fut in done:
        return fut.result()
    if cancel_event is not None and cancel_event.is_set():
        fut.cancel()
        raise asyncio.CancelledError
    # loop restarts → dispatches a NEW download thread every 3s
```

The future creation is inside the polling loop, so any blocking call lasting
longer than `timeout` (3s) gets re-dispatched instead of merely re-polled.
All re-dispatched threads share the same output dir/file, corrupting each other.

## Requirements

1. Fix `_to_thread_with_cancel` so a blocking call is dispatched exactly once;
   the loop only polls completion and cancel_event.
2. On cancellation, the asyncio task is cancelled and `asyncio.CancelledError`
   is raised as before (existing route-layer behavior preserved).
3. Existing call sites (video info fetch, audio download, subtitle extraction,
   transcription, note generation — wherever this helper is used) keep the same
   signature and semantics.
4. No regression: if `func` raises, the exception must still propagate to the
   caller via `fut.result()`.

## Acceptance Criteria

- [ ] Unit test reproducing the bug: a blocking call slower than `timeout`
      executes exactly once (not once per 3s poll).
- [ ] Unit test: cancel_event set mid-call raises `asyncio.CancelledError`.
- [ ] Unit test: exception raised inside `func` propagates to caller.
- [ ] Existing backend test suite passes.
- [ ] Manual verification note: Bilibili download completes without duplicate
      `[download] Destination` restarts / 403 errors (verified by user or logs).

## Non-Goals

- Fixing external scanner noise (`/.git`, `/.env` probes) — unrelated.
- Changing yt-dlp options or cookie handling — cookies worked correctly.
