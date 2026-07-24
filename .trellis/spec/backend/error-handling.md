# Error Handling

> How errors are handled in this project.

---

## Error Types

No custom exception hierarchy — use FastAPI's `HTTPException` for API errors, plain `Exception` with descriptive messages for service-layer errors.

---

## API Error Responses

All API errors follow FastAPI's standard format with a **structured detail** object containing a machine-readable error code and optional interpolation params:

```json
{"detail": {"code": "INVALID_CREDENTIALS"}}
```

With interpolation params:

```json
{"detail": {"code": "TASK_WITH_ID_NOT_FOUND", "params": {"jobId": "abc123"}}}
```

Use the `error_detail(code, **params)` helper from `app/errors.py` to build detail objects. Error codes use `SCREAMING_SNAKE_CASE` and are mapped to i18n keys (`errors.<camelCase>`) on the frontend. The frontend's `translateApiError()` function handles translation and falls back to `errors.unknown` for unrecognized codes, or renders legacy string details as-is for backward compatibility.

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

Services raise exceptions with descriptive messages. Route-level `_process_video_*` functions catch exceptions per-stage, log the full traceback, and store `failed` status in SQLite with a **stable error code** as the progress message (not raw `str(e)`):

```python
# api/routes.py — stable error codes per processing stage
async def _process_video_url(job_id, url, ...):
    try:
        try:
            video_info = await asyncio.to_thread(get_video_info_strict, url, ...)
        except Exception as e:
            logger.exception("...")
            code = getattr(e, "code", None) or "VIDEO_FETCH_FAILED"
            await update_progress(job_id, TaskStage.failed, 0.0, code)
            return
        try:
            transcript = await asyncio.to_thread(transcribe_audio, ...)
        except Exception:
            logger.exception("...")
            await update_progress(job_id, TaskStage.failed, 0.0, "TRANSCRIPTION_FAILED")
            return
        try:
            markdown = await asyncio.to_thread(generate_notes, ...)
        except Exception:
            logger.exception("...")
            await update_progress(job_id, TaskStage.failed, 0.0, "NOTE_GENERATION_FAILED")
            return
        ...
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(f"Task {job_id} failed")
        await update_progress(job_id, TaskStage.failed, 0.0, "PROCESSING_FAILED")
```

### Video Fetch Error Classification

`get_video_info_strict` (in `services/subtitle.py`) raises an exception with a `.code` attribute set by `classify_ytdlp_error(exc)`. The route layer reads it via `getattr(e, "code", None) or "VIDEO_FETCH_FAILED"` and uses it as the progress message.

| Error code | yt-dlp exception signal |
|------------|------------------------|
| `VIDEO_PRIVATE` | "private", "login required" |
| `VIDEO_GEO_RESTRICTED` | "geo", "not available in your country", "region" |
| `VIDEO_NOT_FOUND` | "404", "not found", "unavailable", "deleted" |
| `VIDEO_COOKIE_INVALID` | "cookie", "login" + "required" |
| `VIDEO_FETCH_FAILED` | catch-all fallback |

All five codes must be added to the frontend `TASK_MESSAGE_ERROR_CODES` set and `i18n` locales (`errors.<camelCase>`).

### Additional stable error codes

| Error code | When |
|------------|------|
| `AUDIO_EXTRACTION_FAILED` | Uploaded file audio extraction (ffmpeg) failed — do NOT reuse `VIDEO_FETCH_FAILED` for upload-source tasks |
| `TASK_RECOVERY_MAX_ATTEMPTS` | Recovery skipped a task because `attempt_count >= MAX_TASK_ATTEMPTS` (5) and marked it `failed` |
| `MODELS_FETCH_FAILED` | `/models` endpoint caught an exception; never return `str(e)` to the frontend, only this code |
| `PROVIDER_NOT_CONFIGURED` | `/process`, `/upload`, or `/retry` was called but ASR or LLM provider is incomplete: `api_key`, `api_base`, or `model` is empty (neither user config nor env default). Returned as HTTP 422 before scheduling any work |

These must also be added to `TASK_MESSAGE_ERROR_CODES` (for codes that can appear as task progress messages) and `errors.<camelCase>` i18n keys.

### Non-fatal failures

Thumbnail download failure is non-fatal: wrap `download_thumbnail` in its own try/except, log a warning, and set the thumbnail to `None` — the task continues to generate notes.

Rules:
- Progress `message` MUST be a `SCREAMING_SNAKE_CASE` error code for known failure modes — never `str(e)` (it may leak internal paths, key fragments, or stack details to the frontend).
- **Error detail透传**: When a stage fails, the progress `message` is `"CODE: detail"` where `detail` is a sanitized exception summary (strips `sk-*` API keys, `Bearer` tokens, and cookie content via `_sanitize_error_detail()`; truncated to 200 chars). When `detail` is empty, the message degrades to plain `"CODE"`. The frontend's `translateTaskMessage()` uses prefix matching — splits at the first `": "`, translates the code prefix via i18n, appends the detail suffix. This is backward-compatible: plain `"CODE"` still works.
- The frontend's `translateTaskMessage()` maps these codes to i18n keys via `errors.<camelCase>`.
- Raw exception text stays in server logs only (`logger.exception`).
- **LLM calls** (`note_gen.py`) use `_call_llm()` which retries up to 3 times with exponential backoff (2s, 4s) on `RateLimitError`, `APITimeoutError`, `APIConnectionError`, and 5xx `APIStatusError`. 4xx errors are not retried. Long transcripts are split into chunks (≤ 60000 chars each at line boundaries), each chunk generates a sub-note, and a final LLM call merges them via `_merge_notes()`. If a completion returns `finish_reason == "length"` (truncated by `max_tokens`), `_call_llm()` issues up to 2 continuation requests (appending the assistant prefix + a "continue" user turn) and concatenates the content; a warning is logged if still truncated after 2 continuations.
- **Multi-chunk note generation** reports progress via a `progress_cb` (0.65 start → 0.90 per-chunk → 0.92 merging → 0.95 done) so the SSE stream shows incremental progress instead of stalling at a single value.
- **Cancellation into blocking calls**: `TaskRunner.schedule` creates a `threading.Event` and passes it to the task factory. The event flows into `to_thread`-wrapped service functions (`get_video_info_strict`, `extract_subtitles`, `download_audio_via_ytdlp`, `extract_audio`, `transcribe_audio`, `generate_notes`) so cancellation aborts yt-dlp (via a `progress_hooks` that raises `yt_dlp.utils.DownloadCancelled`) and ffmpeg (`Popen.terminate()`/`kill()`), and skips further ASR/LLM chunks. When a service raises `RuntimeError("cancelled")` from a thread, the route-layer `except Exception` block checks `cancel_event.is_set()` and records `TaskStage.cancelled` instead of `failed`. OpenAI in-flight HTTP calls cannot be interrupted, but chunk-boundary checkpoints prevent new calls from starting after cancellation.
- **Cancellation during `extract_info`**: yt-dlp's `progress_hooks` only fire during downloads, not during `extract_info(download=False)`. The route layer wraps `get_video_info_strict`, `extract_subtitles`, and `download_audio_via_ytdlp` in `_to_thread_with_cancel()`, which polls `cancel_event` every 3 seconds and cancels the asyncio task when the event is set. The underlying yt-dlp thread continues until it returns (then GC'd), but the route layer records `TaskStage.cancelled` promptly.
- Each stage-specific `except` block MUST `return` so the outer catch-all doesn't overwrite the specific code.
- The outer `except Exception` is a last-resort catch-all with a generic `PROCESSING_FAILED` code.
- **Non-error progress messages**: Progress `message` can also be a non-error stage code like `FETCHING_VIDEO_INFO` (written before `get_video_info_strict` runs, so the SSE stream shows an active first step instead of `pending`/"Queued"). These are added to the frontend `TASK_MESSAGE_ERROR_CODES` set and mapped to `errors.<camelCase>` i18n keys the same way as error codes.

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
