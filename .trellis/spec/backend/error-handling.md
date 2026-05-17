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
| 422 | Invalid input (URL not YouTube/Bilibili, unsupported file type) |
| 413 | File exceeds size limit |
| 404 | Task/result not found |
| 500 | Service failure (yt-dlp, ASR, LLM) |

---

## Service Layer Error Handling

Services raise exceptions with descriptive messages. The ARQ worker catches them and stores `failed` status in Redis with the error message.

```python
# services/transcribe.py
except Exception as e:
    raise RuntimeError(f"Whisper API transcription failed: {e}") from e
```

Worker pattern:
```python
try:
    result = await service_call(...)
except Exception as e:
    await set_progress(job_id, TaskProgress(stage="failed", error=str(e)))
    return
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
