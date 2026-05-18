# Error Handling

> How errors are handled in this project.

---

## Error Types

No custom exception hierarchy — use FastAPI's `HTTPException` for API errors, plain `Exception` with descriptive messages for service-layer errors.

---

## API Error Responses

All API errors follow FastAPI's standard format:

```json
{"detail": "descriptive message"}
```

| Status | When |
|--------|------|
| 401 | Invalid/expired token, bad credentials, token reuse |
| 404 | Task/result not found, user not found |
| 409 | Email already registered |
| 413 | File exceeds size limit |
| 415 | Unsupported file type |
| 422 | Invalid input (URL not YouTube/Bilibili) |
| 500 | Service failure (yt-dlp, ASR, LLM) |

---

## Service Layer Error Handling

Services raise exceptions with descriptive messages. Route-level `_process_video_*` functions catch all exceptions, log the full traceback, and store `failed` status in SQLite:

```python
# api/routes.py
async def _process_video_url(job_id, url, ...):
    try:
        ...
    except Exception as e:
        logger.exception(f"Task {job_id} failed: {e}")
        await update_progress(job_id, TaskStage.failed, 0.0, f"Error: {str(e)}")
```

---

## Security Validation

### File Upload Security

```python
# ALWAYS sanitize filenames — prevent path traversal
safe_name = Path(file.filename).name.replace("..", "")

# ALWAYS validate file type — use whitelist, not blacklist
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", ...}
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}
```

### URL Validation

Only YouTube and Bilibili URLs are accepted. Reject all others with 422.

### Auth Error Handling

- Token reuse detection: if a refresh token is used twice, revoke ALL user tokens (see `auth_routes.py`)
- Exception chaining: always use `raise HTTPException(...) from exc`

---

## Common Mistakes

### Don't: Trust user-supplied filenames

```python
# BAD — path traversal vulnerability
file_path = UPLOAD_DIR / file.filename
```

```python
# GOOD — extract basename only
file_path = UPLOAD_DIR / Path(file.filename).name.replace("..", "")
```

### Don't: Skip file type validation

Uploading a `.exe` or `.sh` disguised as video could execute on the server.

### Don't: Catch and swallow exceptions silently

Always propagate errors to the task progress system so the user sees what went wrong.

### Don't: Forget `from exc` when re-raising

```python
# BAD — loses original traceback
except jwt.InvalidTokenError:
    raise HTTPException(status_code=401, detail="Invalid token")

# GOOD — preserves chain
except jwt.InvalidTokenError as exc:
    raise HTTPException(status_code=401, detail="Invalid token") from exc
```
