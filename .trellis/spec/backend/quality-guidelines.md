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

### File cleanup

Temp files (downloaded videos, extracted audio) must be cleaned up after processing, even on error. Use `try/finally` or `tempfile.TemporaryDirectory`:

```python
with tempfile.TemporaryDirectory() as tmpdir:
    audio_path = await asyncio.to_thread(download_audio_via_ytdlp, url, tmpdir)
    # process...
# tmpdir auto-cleaned on exit
```

For uploaded files, delete in `finally`:

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
