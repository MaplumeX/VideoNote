# Quality Guidelines

> Code quality standards for backend development.

---

## Linting

- **Tool**: `ruff` (replaces flake8, isort, pyupgrade)
- **Config**: In `pyproject.toml` `[tool.ruff]`
- **Target**: Python 3.11+, line-length 100
- **Rules**: `E`, `F`, `I`, `UP`, `B`
- **Run from `backend/` directory**: `cd backend/ && uv run ruff check app/`

---

## Type Checking

- Python type hints on all function signatures
- Pydantic models for all API boundaries
- No `Any` in public interfaces
- Use `str | None` (not `Optional[str]`) for modern union syntax

---

## Forbidden Patterns

### Don't: Subprocess with unsanitized user input

```python
# BAD — command injection
subprocess.run(["ffmpeg", "-i", user_url, ...])

# GOOD — yt-dlp handles URL safety; for local files, validate path first
subprocess.run(["ffmpeg", "-i", validated_path, ...], check=True, capture_output=True)
```

### Don't: Blocking calls in async context

yt-dlp and ffmpeg are sync — always run them with `asyncio.to_thread()` inside async handlers.

```python
# GOOD
subtitle_text = await asyncio.to_thread(extract_subtitles, url)
transcript = await asyncio.to_thread(transcribe_audio, audio_path, api_key=..., ...)
```

### Don't: Hardcode API keys

All credentials in `.env`, loaded via `app/config.py`.

### Don't: Use bcrypt directly in async context

bcrypt is CPU-intensive and blocks the event loop. Always wrap with `asyncio.to_thread()`:

```python
async def hash_password(password: str) -> str:
    hashed = await _run_bcrypt(bcrypt.hashpw, password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")
```

---

## Required Patterns

> **Deprecated subsections (C4)**: "Scenario: yt-dlp Shared Options" (replaced by
> `app/pipeline/subprocess_util.build_ytdlp_args` + CLI subprocess invocation),
> "Async task delegation" (replaced by `app/pipeline/runner.PipelineTaskRunner`
> + `orchestrator.schedule_task`), and "Progress reporting" (replaced by the
> phase + within-phase `PhaseProgressTracker` model — the global 0–1 progress
> value is abolished; see `docs/pipeline-contract.md` §2) describe the deleted
> legacy chain. The "Pipeline Stage Implementation Rules" section below is the
> authoritative guidance for `app/pipeline/**`.

### Scenario: yt-dlp Shared Options

#### 1. Scope / Trigger
- Trigger: Any backend code that calls `yt_dlp.YoutubeDL`.
- Keep yt-dlp integration options centralized so audio, subtitles, title lookup, and metadata lookup behave consistently.

#### 2. Signatures
- Use `app.services.subtitle._ydl_opts(**extra: object) -> dict` to construct `YoutubeDL` options.

#### 3. Contracts
- `YT_DLP_PROXY`: optional proxy URL passed as `proxy`.
- `YT_DLP_COOKIES_FROM_BROWSER`: optional browser cookie spec using yt-dlp syntax `BROWSER[+KEYRING][:PROFILE][::CONTAINER]`, passed as `cookiesfrombrowser`.
- `YT_DLP_COOKIES_FILE`: optional Netscape cookies file path, passed as `cookiefile`.

#### 4. Validation & Error Matrix
- Invalid `YT_DLP_COOKIES_FROM_BROWSER` format -> service raises `ValueError`; route-level task processing records failed status.
- Unsupported browser/keyring -> yt-dlp raises during extraction; route-level task processing records failed status.

#### 5. Good/Base/Bad Cases
- Good: `YT_DLP_COOKIES_FROM_BROWSER=chrome` and all yt-dlp calls inherit browser cookies.
- Base: no cookie env vars set and yt-dlp runs anonymously.
- Bad: a new `yt_dlp.YoutubeDL({...})` call bypasses `_ydl_opts`, so proxy/cookies work in one feature but fail in another.

#### 6. Tests Required
- Unit tests for `_ydl_opts` must assert proxy, browser cookies, cookies file, and caller-provided options are preserved.
- Parser tests must cover browser profile/keyring/container syntax and invalid syntax.

#### 7. Wrong vs Correct

Wrong:

```python
with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
    ...
```

Correct:

```python
with yt_dlp.YoutubeDL(_ydl_opts(quiet=True)) as ydl:
    ...
```

### Annotated type alias for FastAPI Depends

Use `Annotated` type aliases instead of `Depends()` in parameter defaults (avoids B008 ruff violation):

```python
from typing import Annotated
from fastapi import Depends

CurrentUser = Annotated[TokenData, Depends(get_current_user)]
AuthCredentials = Annotated[HTTPAuthorizationCredentials, Depends(security)]

@router.get("/me")
async def get_me(user: CurrentUser):
    ...
```

### Exception chaining

Always use `raise ... from exc` when re-raising caught exceptions:

```python
except jwt.InvalidTokenError as exc:
    raise HTTPException(status_code=401, detail="Invalid token") from exc
```

### Async task delegation

Long-running video processing tasks are launched via `asyncio.create_task`:

```python
asyncio.create_task(_process_video_url(job_id, url, language=language, user_id=user.user_id))
```

### Progress reporting

All long-running tasks report progress to SQLite for SSE consumption:

```python
await update_progress(job_id, TaskStage.transcribing, 0.4, "Transcribing audio...")
```

Progress values MUST be monotonic non-decreasing within a single task — never write a smaller
value than the previous one. This applies across stage transitions, especially when falling
back from subtitle extraction to ASR: the fallback path must continue from the current value,
not reset to a lower one. Use distinct sub-ranges per stage (e.g. extracting_subtitles 0.10–0.30,
downloading 0.15–0.25, transcribing 0.30–0.60, generating_notes 0.65–0.95 for URL tasks;
extraction 0.05–0.15, transcribing 0.20–0.60, generating_notes 0.65–0.95 for upload tasks).

Use `TaskStage.downloading` for audio extraction of uploaded files (NOT `transcribing`)

### File cleanup

Temp files (downloaded videos, extracted audio) must be cleaned up at terminal
states — **but the terminal state decides what "cleaned up" means** (see the
retry/resume contract below). Use `try/finally` or `tempfile.TemporaryDirectory`
for in-stage scratch files:

```python
with tempfile.TemporaryDirectory() as tmpdir:
    audio_path = await asyncio.to_thread(download_audio_via_ytdlp, url, tmpdir)
    # process...
# tmpdir auto-cleaned on exit
```

#### Terminal-state file retention contract (failed tasks stay retryable)

Per-job recovery files (the pipeline WAV at `tmp/videonote_pipeline_audio/{job_id}.wav`
and upload inputs under `UPLOAD_DIR`) are retained or deleted by terminal state:

| Terminal state | WAV | Upload input | Who cleans |
|---|---|---|---|
| `complete` | deleted | deleted + `input_file_path` NULL | `_finalize_complete` → `_cleanup_files` |
| `cancelled` | deleted | deleted + `input_file_path` NULL | `_finalize_cancelled` / `_maybe_cancelled` → `_cleanup_files` |
| `failed` | **retained** | **retained** (path stays in DB) | `db.cleanup_failed_task_files` after 7 days (also deletes the WAV) |
| task deleted (DELETE) | deleted | deleted | `cancel_or_delete_task` route |

Why: `POST /tasks/{id}/retry` resumes from the persisted checkpoint; deleting
the WAV/upload input at failure time forces a full restart and makes upload
retries fail outright (`neither url nor input_path in stage context`). When the
WAV is missing at retry, the orchestrator rewinds **only to the audio phase**
and keeps resume semantics, so fetching/subtitle still short-circuit on stored
artifacts.

Don't add file deletion to `_finalize_failed` — a future "cleanup" there
silently reintroduces the retry-from-scratch bug.

For uploaded files in non-pipeline code, delete in `finally`:

```python
try:
    # process file_path
    ...
finally:
    Path(file_path).unlink(missing_ok=True)
```

### Provider config with encrypted keys

User API keys must be encrypted before storing, decrypted when reading:

```python
encrypted = encrypt_api_key(plaintext_key)
decrypted = decrypt_api_key(encrypted)
```

---

## Testing Requirements

- Pytest for backend tests (with `pytest-asyncio`, `asyncio_mode = "auto"`)
- Test service functions with mocked external APIs (OpenAI, yt-dlp)
- Test API endpoints with FastAPI `TestClient`

---

## Pipeline Stage Implementation Rules (C2/C3, supersedes sync-service rules for pipeline code)

> **C4 update**: the parenthetical below about the legacy `app/services/`
> sync + `to_thread` path remaining valid no longer applies — the legacy chain
> was deleted in C4. These rules are now the only pipeline guidance; the
> deprecated sync-service rules elsewhere in this file are kept for historical
> reference only.

Rules below apply to `app/pipeline/**` (the new core pipeline). The legacy
`app/services/**` sync + `to_thread` pattern remains valid only for the legacy
path until C4 deletes it.

### Forbidden in pipeline code
- `threading.Event` for cancellation — use asyncio cancellation + cancel handles.
- `asyncio.to_thread` wrapping yt-dlp/ffmpeg — both run as managed subprocesses via `pipeline/subprocess_util.run_managed_process`.
- `shell=True` — subprocesses use `create_subprocess_exec` with list args only.
- Sync `[OI]` clients — use `Async[OI]` (cancellation propagates into in-flight requests).
- `time.sleep` — use `asyncio.sleep` (retry backoff in `LLMClient` is `asyncio.sleep(2**(attempt+1))`).

### Required
- Subprocess cancellation path: on `CancelledError` or timeout, terminate → (5s grace) → kill, then re-raise. Proven by real-subprocess tests (`test_subprocess_util.py`): cancel terminates in <3s with no residual process.
- yt-dlp is invoked via CLI subprocess (`--dump-json` / `--no-download` / `--write-subs --write-auto-subs` / `-f bestaudio/best`); shared args are built centrally in `subprocess_util.build_ytdlp_args` (proxy/cookie priority: per-user cookiefile > browser cookies > config file). Never use the yt-dlp Python API in pipeline code (un-interruptible `extract_info` was a historical bug source).
- yt-dlp error text is classified by `subprocess_util.classify_ytdlp_error(text) -> ErrorCode` (keyword table identical to the legacy one).
- Stage outputs: DB-worthy data goes in `StageResult.outputs` (artifact kinds); ephemeral cross-stage data (e.g. `audio_path`, final `notes`) goes in `StageResult.extra`; stage inputs like `url`/`input_path` arrive via `StageContext.extra`. Stages never write SQLite directly.
- WAV files produced by AudioStage live in `tmp/videonote_pipeline_audio/{job_id}.wav` (per-job names — a shared `audio.wav` name caused overwrites under concurrency); cleanup is the orchestrator's (C4) responsibility, split by terminal state — see the terminal-state file retention contract above (failed retains the WAV for checkpoint-resumed retry; delayed cleanup after 7 days is `db.cleanup_failed_task_files`, which re-implements the WAV path rule locally as `_wav_path_for` to avoid a db → pipeline import cycle — keep the two rules in sync).
- `except asyncio.CancelledError: raise` must precede `except Exception` in every stage/retry loop — swallowing CancelledError in a retry loop silently breaks cancellation.
- Prompts in `stages/notegen.py` are character-for-character snapshots of the legacy `services/note_gen.py` prompts, locked by snapshot tests. Do not "improve" them without a task that explicitly changes note-generation behavior.
