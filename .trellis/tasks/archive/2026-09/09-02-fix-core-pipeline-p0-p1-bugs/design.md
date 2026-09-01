# Design: Fix core pipeline P0/P1 bugs

All six fixes are localized; no cross-cutting design changes. One shared principle:
mirror existing defensive patterns in the codebase (`_safe_upload_path` containment
check, cookie-decrypt warning log) instead of inventing new ones.

## P0-1 — audio.py retcode misuse

`download_audio_via_ytdlp` runs yt-dlp in two modes:

- `ydl.download([url])` → returns `int` retcode (0 = ok).
- `ydl.process_ie_result(info, download=True)` → returns the resolved info **dict**.

Current code assigns either into `retcode` then checks `retcode != 0` — always True for
a dict.

**Fix**: read `ydl._download_retcode` after either call (this is exactly what
`download()` returns internally; both code paths funnel into `__download_wrapper` which
sets `_download_retcode`). Keep the same RuntimeError message shape. The private-attr
access is acceptable here: it is the only stable cross-path signal, and the module
already depends on yt-dlp internals (`process_ie_result` reuse itself is a
semi-internal API). Alternative considered: drop the retcode check and rely on the
"audio file not found" check — rejected because it loses genuine failure diagnostics
(e.g. partial download with retcode 1 still leaves a file).

## P0-2 — main.py SPA fallback traversal

Replace naive join with containment check:

```python
resolved_root = frontend_dist.resolve()
candidate = (frontend_dist / full_path).resolve()
if full_path and candidate.is_file() and resolved_root in candidate.parents:
    return FileResponse(candidate)
```

Note `in parents` (strict containment) mirrors `_safe_upload_path`; serving the dist
root itself as a file is meaningless. `resolve()` also collapses `..` segments, so the
encoded-relative variant is covered. Percent-encoded absolute paths (`/%2Fetc%2Fpasswd`)
become `/etc/passwd` after join → resolve → containment fails → falls through to
index.html. Symlinks: `resolve()` follows them; a symlinked dist content pointing
outside would still be blocked. Compute `resolved_root` once at module level (dist is
fixed at startup).

## P1-3 — upload cleanup on disconnect

Wrap the `open/write` loop:

```python
try:
    with open(file_path, "wb") as f:
        while chunk := await file.read(...):
            ...size check (already unlinks on 413)...
            f.write(chunk)
except Exception:
    file_path.unlink(missing_ok=True)
    raise
```

Client disconnect surfaces as an exception from `await file.read` (or a CancelledError
on request teardown). Re-raise so FastAPI's normal error handling runs; the only added
behavior is deleting the partial file. Do not catch BaseException — CancelledError
inherits from BaseException in 3.11 and should still run cleanup via the same except?
Careful: `except Exception` does NOT catch CancelledError in Python ≥3.8. Use
`try/except BaseException: unlink; raise` to cover task cancellation too, or
try/finally with a success flag. Chosen: success-flag + finally — clearest and catches
both.

## P1-4 — Retry button for cancelled tasks

Frontend-only: change `isFailed` to `stage === "failed" || stage === "cancelled"`
split into two flags: `isFailed` (failed only) drives Retry; cancelled keeps its error
display but hides Retry. Keep i18n untouched.

## P1-5 — cleanup cutoff format

Add a helper in db.py:

```python
def _sqlite_utc_timestamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")
```

Use it for both cleanup cutoffs (they compare against `created_at`, which is always
`CURRENT_TIMESTAMP`-formatted). `updated_at` (isoformat, app-written) is NOT compared
anywhere — leave as-is. Same-second boundary: `CURRENT_TIMESTAMP` has second precision;
cutoff has second precision too; strict `<` keeps "delete only strictly older" —
correct.

## P1-6 — SECRET_KEY diagnostics

1. `main.py` lifespan (or config import site — chosen: lifespan, keeps config pure):
   `if not os.getenv("SECRET_KEY"): logger.warning(...)` with explicit consequence text
   (encrypted provider keys/cookies become unreadable after restart).
   config already exposes `SECRET_KEY`; detect the random-default case by checking the
   env var directly (SECRET_KEY itself cannot distinguish generated vs provided).
   Add a `SECRET_KEY_IS_RANDOM` flag in config.py computed once.
2. `_get_user_provider`: catch-log-warn on decrypt failure, mirroring
   `_get_user_cookiefile`'s existing warning (include user_id + category + hint that
   SECRET_KEY may have changed).

## Test strategy

- P0-1: unit test with mocked `yt_dlp.YoutubeDL` whose `process_ie_result` writes a
  fake audio file and returns a dict; assert no raise + wav path returned. Also a
  retcode=1 failure case asserts RuntimeError.
- P0-2: TestClient tests against a temp dist dir: normal file 200, traversal variants
  fall back to index.html (200 but content is index), file-outside-dist not served.
- P1-3: monkeypatch `UploadFile.read` to raise mid-loop; assert no file remains.
- P1-4: extend/adjust existing frontend tests if present; otherwise a small component
  test asserting Retry absent for cancelled stage. (vitest is configured in frontend.)
- P1-5: unit test comparing `_sqlite_utc_timestamp(now)` vs a same-moment
  CURRENT_TIMESTAMP string: assert `created_at < cutoff` is False for same-day rows.
- P1-6: unit test that `_get_user_provider` logs a warning when decryption raises
  (mock decrypt to throw); caplog-based.

## Risks / rollback

- P0-1 uses `ydl._download_retcode` (private attr). Risk: yt-dlp API drift — mitigated
  by a test asserting the attribute exists on the pinned version; fallback in code:
  `getattr(ydl, "_download_retcode", 0)`.
- All fixes are single-file, revertable independently.
