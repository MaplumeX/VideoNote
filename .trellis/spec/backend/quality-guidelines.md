# Quality Guidelines

> Code quality standards for backend development.

---

## Linting

- **Tool**: `ruff` (replaces flake8, isort, pyupgrade)
- **Config**: In `pyproject.toml` `[tool.ruff]`
- **Run from `backend/` directory**: `cd backend/ && uv run ruff check app/`

---

## Type Checking

- Python type hints on all function signatures
- Pydantic models for all API boundaries
- No `Any` in public interfaces

---

## Forbidden Patterns

### Don't: Subprocess with unsanitized user input

```python
# BAD — command injection
subprocess.run(["ffmpeg", "-i", user_url, ...])
```

```python
# GOOD — yt-dlp handles URL safety; for local files, validate path first
subprocess.run(["ffmpeg", "-i", validated_path, ...], check=True, capture_output=True)
```

### Don't: Blocking calls in async context

yt-dlp and ffmpeg are sync — always run them with `asyncio.to_thread()` or `loop.run_in_executor()` inside async handlers.

### Don't: Hardcode API keys

All credentials in `.env`, loaded via `app/config.py`.

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

All video processing (1-10 min tasks) goes through ARQ, never FastAPI BackgroundTasks.

```python
job = await redis.enqueue_job("process_video_url", url, platform)
```

### Progress reporting

All long-running tasks report progress to Redis for SSE consumption:

```python
await set_progress(job_id, TaskProgress(
    stage="transcribing",
    progress=50,
    message="Transcribing audio via Whisper API..."
))
```

### File cleanup

Temp files (downloaded videos, extracted audio) must be cleaned up after processing, even on error. Use `try/finally`.

---

## Testing Requirements

- Pytest for backend tests
- Test service functions with mocked external APIs (OpenAI, yt-dlp)
- Test API endpoints with FastAPI `TestClient`
