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

### File-Serving Endpoint Security

When serving local files via `FileResponse`, string-based filename checks alone are insufficient — use `resolve()` + `startswith()` to verify the resolved path stays within the intended directory:

```python
# BAD — string checks can be bypassed on some platforms
if ".." in filename or "/" in filename:
    raise HTTPException(status_code=400)
path = UPLOAD_DIR / "subdir" / filename
return FileResponse(path)

# GOOD — string checks + resolved path verification
if ".." in filename or "/" in filename or "\\" in filename:
    raise HTTPException(status_code=400)
path = (UPLOAD_DIR / "subdir" / filename).resolve()
if not str(path).startswith(str((UPLOAD_DIR / "subdir").resolve())):
    raise HTTPException(status_code=404)
return FileResponse(path)
```

### External Resource Anti-Hotlinking

Some CDNs (e.g., Bilibili's `hdslb.com`) enforce Referer-based anti-hotlinking. Frontend `<img>` tags loading these URLs directly will get 403. **Always proxy external images through the backend** — download at ingestion time, serve via a local file endpoint.

```python
# BAD — frontend loads external CDN directly, blocked by anti-hotlinking
thumbnail_url = info.get("thumbnail")  # e.g. https://i0.hdslb.com/...

# GOOD — backend downloads and serves locally
filename = download_thumbnail(info.get("thumbnail"))
# For Bilibili URLs, set Referer: https://www.bilibili.com
```

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

### Don't: Serve local files with only string-based path checks

String checks (`".."`, `"/"`) can miss edge cases. Always verify the **resolved absolute path** stays within the target directory.

### Don't: Skip file type validation

Uploading a `.exe` or `.sh` disguised as video could execute on the server.

### Don't: Catch and swallow exceptions silently

Always propagate errors to the task progress system so the user sees what went wrong.

### Don't: Use FastAPI's `UploadFile | None` + `PydanticModel | None` together

FastAPI cannot parse both a file upload and a JSON body in the same endpoint. If you declare both, one will always be `None`. Instead, use `request: Request` and manually parse by `Content-Type`:

```python
# BAD — body is always None when file is present, and vice versa
@router.put("/{platform}")
async def save_cookie(
    platform: str,
    file: UploadFile | None = None,
    body: CookieSaveRequest | None = None,
):
    ...

# GOOD — manually parse by Content-Type
@router.put("/{platform}")
async def save_cookie(platform: str, request: Request):
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        file = form.get("file")
        ...
    elif "application/json" in content_type:
        body = await request.json()
        ...
```

### Don't: Forget `from exc` when re-raising

```python
# BAD — loses original traceback
except jwt.InvalidTokenError:
    raise HTTPException(status_code=401, detail="Invalid token")

# GOOD — preserves chain
except jwt.InvalidTokenError as exc:
    raise HTTPException(status_code=401, detail="Invalid token") from exc
```
