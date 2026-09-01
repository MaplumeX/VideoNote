# PRD: Fix core pipeline P0/P1 bugs from review

## Background

A read-only review of the core pipeline (task lifecycle, subtitle/audio/transcribe/note-gen
stages, SPA serving) found 2 P0 and 4 P1 bugs. All P0 bugs have been reproduced with
executable evidence; the P1 bugs are logic/resource defects confirmed by code inspection.
Existing test suite passes (74 tests) — the bugs live in paths covered only by mocks or
not covered at all.

## Scope

Fix the following bugs. In scope: backend fixes + minimal frontend fix + regression tests.

### P0-1: `process_ie_result` return value misused as retcode

- **File**: `backend/app/services/audio.py` (`download_audio_via_ytdlp`)
- **Defect**: `ydl.process_ie_result(info, download=True)` returns the resolved info
  **dict**, not an int retcode. `retcode != 0` is always True for a dict, so the function
  always raises `RuntimeError("yt-dlp download failed (retcode={...})")`.
- **Impact**: Every URL task whose video has no subtitles (the ASR fallback path, the
  pipeline's main path) fails 100%.
- **Reproduction**: mock-verified (see review session); `info` is always non-None in
  `_process_video_url`.

### P0-2: SPA fallback path traversal (arbitrary file read)

- **File**: `backend/app/main.py` (`spa_fallback`)
- **Defect**: `candidate = frontend_dist / full_path` — starlette percent-decodes the
  path param, so `/%2Fetc%2Fpasswd` yields `full_path = "/etc/passwd"` and `Path / abs`
  replaces the base entirely. Encoded `..%2f..%2f` traversal also works.
- **Impact**: unauthenticated arbitrary file read on single-image production deployments
  (uvicorn-direct exposure; proxies that forward `%2F` are also affected).
- **Fix direction**: resolve and verify containment (`frontend_dist.resolve()` in
  `candidate.parents`), mirroring `_safe_upload_path` in routes.py.
- **Evidence**: reproduced with Starlette TestClient — `/etc/passwd` and a file outside
  the dist dir were both served with 200.

### P1-3: Abandoned upload files leak on client disconnect

- **File**: `backend/app/api/routes.py` (`upload_video`)
- **Defect**: the chunked write loop is not exception-guarded. If `await file.read(...)`
  raises (client disconnect), the partially written file stays in `UPLOAD_DIR` with no
  task row referencing it — never cleaned up (compare: the 413 branch unlinks).
- **Fix direction**: wrap the write loop in try/except, unlink on failure.

### P1-4: Cancelled tasks show a Retry button that the backend rejects

- **File**: `frontend/src/pages/NewNotePage.tsx`
- **Defect**: `isFailed = stage === "failed" || stage === "cancelled"` shows Retry for
  cancelled tasks, but `POST /tasks/{job_id}/retry` requires stage `failed` (409
  `ONLY_FAILED_CAN_RETRY` otherwise). Clicking Retry on a cancelled task only surfaces
  an error.
- **Fix direction**: show Retry only for `stage === "failed"`. Optionally the backend
  may also allow retry of cancelled tasks — NOT in scope unless trivially safe; the
  minimal, consistent fix is frontend-only.

### P1-5: Timestamp format mismatch in cleanup queries

- **File**: `backend/app/db.py` (`cleanup_failed_task_files`, `cleanup_old_terminal_tasks`)
- **Defect**: `created_at` is written by SQLite `CURRENT_TIMESTAMP` (`YYYY-MM-DD HH:MM:SS`,
  no timezone), but the cutoff uses Python `isoformat()` (`YYYY-MM-DDTHH:MM:SS+00:00`).
  String comparison: `' ' (0x20) < 'T' (0x54)`, so same-day rows compare "older" than
  the cutoff and get deleted ~1 day early.
- **Fix direction**: build the cutoff in the same SQLite format (`YYYY-MM-DD HH:MM:SS`,
  UTC) for comparisons against `created_at`. (A full timestamp-format migration is out
  of scope; keep the change minimal and behavior-correct.)

### P1-6: Random SECRET_KEY silently invalidates encrypted data after restart

- **File**: `backend/app/config.py`, `backend/app/crypto.py`, `backend/app/api/routes.py`
- **Defect**: `SECRET_KEY` defaults to a per-boot random value; Fernet key is derived at
  import time. After restart, all stored API keys/cookies fail to decrypt. Decryption
  failures are swallowed silently (`_get_user_provider` has no logging at all), so users
  see silent fallback to env defaults / missing cookies with no explanation.
- **Fix direction**:
  1. Fail fast at startup: when `SECRET_KEY` is unset, log a prominent warning at
     startup (crashing on default may break quick local runs — decide: warning is the
     minimal safe behavior for this fix; document in compose/env template).
  2. Add a warning log in `_get_user_provider` when decryption fails (parity with the
     existing cookie warning), including a hint that SECRET_KEY changed.

## Out of scope

- P2 findings from the review (SSRF surface of /models, task_runner race, SSE
  "Task not found" shape, register race, sqlite transaction interleave, fire-and-forget
  progress futures).
- Full timestamp-format normalization across the schema.
- Allowing retry of cancelled tasks (backend behavior change).

## Acceptance Criteria

1. **P0-1**: `download_audio_via_ytdlp` with a mocked `process_ie_result` returning a
   dict no longer raises; retcode semantics are validated (unit test). A regression test
   covers the info-reuse path asserting success.
2. **P0-2**: `spa_fallback` rejects `/%2Fetc%2Fpasswd`, `/..%2f..%2f..` style traversal,
   and `//../` variants (no file outside `frontend_dist` is ever served); normal files
   and index.html fallback still work (unit tests).
3. **P1-3**: an exception mid-upload (simulated client disconnect) leaves no partial
   file in `UPLOAD_DIR` (unit test).
4. **P1-4**: Retry button is not rendered for cancelled tasks (frontend test or
   typecheck-level assertion; minimal).
5. **P1-5**: cleanup cutoffs compare against `CURRENT_TIMESTAMP`-formatted values;
   unit test demonstrates same-day created_at is NOT older than a same-moment cutoff.
6. **P1-6**: startup logs a warning when SECRET_KEY is unset; decryption failure in
   `_get_user_provider` logs a warning (unit-testable).
7. All existing tests pass; `ruff check app/` clean.

## Constraints

- Python 3.11+, backend changes under `backend/app/`; follow `.trellis/spec/backend/*`.
- No schema migrations required.
- Keep fixes minimal and behavior-focused; no refactors beyond the bug fixes.
