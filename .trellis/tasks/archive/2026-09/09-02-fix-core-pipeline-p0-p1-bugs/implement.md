# Implementation Plan: Fix core pipeline P0/P1 bugs

## Ordering

P0-1 → P0-2 → P1-3 → P1-5 → P1-6 → P1-4 (backend first, frontend last).
Each step is independently verifiable and revertable.

## Checklist

### Step 1 — P0-1 audio retcode (backend/app/services/audio.py)
- [ ] Replace `retcode = ydl.process_ie_result(...)` misuse: after either branch, read
      `retcode = getattr(ydl, "_download_retcode", 0)`.
- [ ] Keep the existing `retcode != 0` RuntimeError path.
- [ ] Add `tests/test_audio_download.py`:
      - info-reuse success case (mock YDL writes fake audio, `process_ie_result`
        returns dict; `extract_audio` mocked) — must not raise.
      - `_download_retcode = 1` case — must raise RuntimeError.

### Step 2 — P0-2 SPA fallback (backend/app/main.py)
- [ ] Compute `frontend_dist_resolved = frontend_dist.resolve()` at module level
      (inside the `if frontend_dist.is_dir():` block).
- [ ] In `spa_fallback`: resolve candidate, serve only when
      `candidate.is_file() and frontend_dist_resolved in candidate.parents`.
- [ ] Add `tests/test_spa_fallback.py` with a temp dist dir:
      - `GET /favicon.ico` → 200 file content.
      - `GET /%2Fetc%2Fpasswd` → serves index.html, never /etc/passwd.
      - `GET /..%2f..%2fetc%2fpasswd` → index.html fallback.
      - `GET /anything` (missing) → index.html.
      - A file outside dist must never be served.

### Step 3 — P1-3 upload cleanup (backend/app/api/routes.py)
- [ ] Wrap upload write loop with success-flag + `finally: unlink if not success`.
- [ ] Add test in `tests/test_pipeline_bugs.py` (or new file): simulate read raising
      after first chunk; assert no leftover file in a tmp UPLOAD_DIR.
      Note: routes read `UPLOAD_DIR` at import — monkeypatch via tmp dir + reload or
      patch `routes.UPLOAD_DIR` (module attribute) — check which the module references
      inside the handler (`UPLOAD_DIR / f"..."` — monkeypatch `routes.UPLOAD_DIR`).

### Step 4 — P1-5 cleanup cutoff format (backend/app/db.py)
- [ ] Add `_sqlite_utc_timestamp()` helper; use in both cleanup functions.
- [ ] Unit test: same-instant `created_at` (CURRENT_TIMESTAMP format) is not `<`
      same-instant cutoff; older timestamp is.

### Step 5 — P1-6 SECRET_KEY diagnostics
- [ ] `backend/app/config.py`: add `SECRET_KEY_IS_RANDOM: bool` flag.
- [ ] `backend/app/main.py` lifespan: warn once when flag is true.
- [ ] `backend/app/api/routes.py` `_get_user_provider`: log warning on decrypt failure
      (parity with `_get_user_cookiefile`).
- [ ] Tests: caplog warning on decrypt failure in `_get_user_provider`.

### Step 6 — P1-4 Retry button (frontend/src/pages/NewNotePage.tsx)
- [ ] Split `isFailed` into `isFailed` (failed only) and cancelled handling; Retry
      button only when `isFailed`.
- [ ] Adjust/add vitest test if a test file exists for the page; otherwise add a
      minimal render test with stage cancelled asserting no Retry button.

## Validation commands

```bash
cd backend && uv run python -m pytest tests/ -q
cd backend && uv run ruff check app/
cd frontend && npm run test        # vitest (verify script name in package.json)
cd frontend && npm run build       # typecheck via build
```

## Review gates

- After Step 2 (both P0s done): run full backend suite before continuing.
- After Step 6: full validation matrix above.

## Rollback points

Each step is a single-file change; `git checkout -- <file>` reverts independently.
Commit per logical group (P0 batch, P1 batch) or one commit per fix — prefer one
commit per fix for reviewability.
