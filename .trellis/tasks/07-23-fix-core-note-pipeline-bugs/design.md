# Design: fix core note pipeline bugs

## Architecture Overview

All changes are in the backend `app/` package, except R5 and R6 which add
frontend i18n keys and tolerate empty title/thumbnail in the submit response.

### Affected files

| File | Changes |
|------|---------|
| `app/services/subtitle.py` | R1: add SRT/VTT → `#t=` converter |
| `app/services/transcribe.py` | R2: accept language, default `"en"` instead of `"zh"` |
| `app/api/routes.py` | R2–R6: pass language, defer video_info, keep upload files, error codes |
| `app/errors.py` | R5: no code change (existing `error_detail` is for HTTP; progress messages use raw code strings) |
| `frontend/src/i18n/locales/en.json` | R5: add error-code translations |
| `frontend/src/i18n/locales/zh-CN.json` | R5: add error-code translations |
| `frontend/src/api/client.ts` | R5: extend `TASK_MESSAGE_ERROR_CODES` set |

---

## R1 — SRT/VTT → timestamp-link conversion

### Current data flow

```
subtitle.py extract_subtitles() → raw SRT/VTT string
routes.py: has_timestamps = "#t=" in transcript  → False for SRT
note_gen.py: selects _PROMPTS_WITHOUT_TIMESTAMPS
```

### New data flow

```
subtitle.py extract_subtitles() → _format_subtitles_as_transcript()
  parses SRT/VTT → "[HH:MM:SS](#t=SECONDS) text\n..."
routes.py: has_timestamps = "#t=" in transcript  → True
note_gen.py: selects _PROMPTS_WITH_TIMESTAMPS
```

### Conversion function

Add `_srt_to_transcript(raw: str) -> str | None` in `subtitle.py`:

- Split into blocks separated by blank lines.
- Each block: optional index line, timestamp line `HH:MM:SS,mmm --> HH:MM:SS,mmm` (SRT) or `HH:MM:SS.mmm --> ...` (VTT), then one+ text lines.
- Extract start time, convert to seconds.
- Format as `[HH:MM:SS](#t=SECONDS) text`.
- Concatenate all blocks with `\n`.
- If no valid timestamp blocks found, return `None` (fall back to ASR).
- Skip `WEBVTT` header and `NOTE` blocks in VTT.

Called inside `extract_subtitles()` before returning, replacing the raw SRT/VTT return.

### Edge cases

- VTT with cue headers (e.g. `00:00:01.000 position:10%`) — strip after the
  timestamp portion.
- Multi-line cue text — join with space.
- Empty/malformed input — return `None`.

---

## R2 — Pass user language to transcribe_audio

### Mapping

`_normalize_language()` already maps to `"en"` or `"zh-CN"`. Add a helper:

```python
def _asr_language(note_lang: str) -> str:
    return "zh" if note_lang.startswith("zh") else "en"
```

### Call sites

`_process_video_url` and `_process_video_file` both call `transcribe_audio`:
add `language=_asr_language(language)` to both `asyncio.to_thread(...)` calls.

`transcribe_audio` default changes from `language="zh"` to `language="en"`,
but callers always pass the value so the default is just a safety net.

---

## R3 + R6 — Defer `get_video_info` to background

### Current `process_video` flow

```
1. detect_video_platform(url)
2. _get_user_cookiefile()          ← network/decrypt
3. get_video_info(url)              ← yt-dlp, 10–30s  (BLOCKING)
4. download_thumbnail(url)         ← HTTP
5. create_task(...)
6. task_runner.schedule(...)
7. return ProcessResponse(job_id, title, thumbnail, platform)
```

### New `process_video` flow

```
1. detect_video_platform(url)
2. create_task(job_id, ..., title=None, thumbnail_url=None)
3. task_runner.schedule(_process_video_url(job_id, url, language, user_id))
4. return ProcessResponse(job_id, title="", thumbnail_url="", platform=platform)
```

### Changes to `_process_video_url`

Move cookie resolution, `get_video_info`, and `download_thumbnail` inside the
background job:

```
1. cookiefile = _get_user_cookiefile(user_id, url)
2. video_info = get_video_info(url, cookiefile)    ← called ONCE
3. download_thumbnail(video_info.thumbnail_url)
4. update task row: title, thumbnail_url           ← NEW: persist back to DB
5. update_progress(...)  ← continue as before
6. ...subtitle/ASR/LLM...
```

Add a `db.update_task_meta(job_id, title, thumbnail_url)` helper that updates
the `title` and `thumbnail_url` columns.

### Changes to `retry_task`

Same pattern: create task immediately, defer video_info to the background job.

### ProcessResponse contract

`title` and `thumbnail_url` default to `""` in the schema. Frontend already
handles nullable `title` in `TaskListItem`. The SSE `progress` event sends
`stage/progress/message` only — it does NOT send title/thumbnail. The frontend
gets title/thumbnail from the task list or `get_single_task`.

**Frontend change**: after `submitUrl()` returns, the frontend should not
assume `title` or `thumbnail_url` are populated. It should display the job_id
and connect SSE. The title will appear in the history list / task detail once
the background job populates it.

### Error handling for deferred video_info

If `get_video_info` fails in the background job:
- `video_info` returns `{"title": None, "thumbnail_url": None}` (existing
  behavior — it catches exceptions and returns None values).
- If the URL is completely invalid (yt-dlp raises), the exception propagates
  to the `_process_video_url` catch block, which writes `VIDEO_FETCH_FAILED`
  as the progress message.

---

## R4 — Keep upload file on failure; allow retry

### `_process_video_file` finally block

Current:
```python
if task is None or task["stage"] in (complete, failed, cancelled):
    Path(file_path).unlink(missing_ok=True)
    await clear_task_input_file(job_id)
```

New:
```python
if task is None or task["stage"] in (complete, cancelled):
    Path(file_path).unlink(missing_ok=True)
    await clear_task_input_file(job_id)
# On failure: keep the file and input_file_path for retry
```

### `retry_task`

Remove the `ONLY_URL_CAN_RETRY` guard. Add upload-task retry:

```python
if task["source_type"] == "url" and task.get("video_url"):
    ...  # existing URL retry logic
elif task["source_type"] == "upload":
    file_path = _safe_upload_path(task.get("input_file_path"))
    if not file_path or not file_path.is_file():
        raise HTTPException(422, error_detail("UPLOAD_FILE_MISSING"))
    create_task(new_job_id, source_type="upload", input_file_path=str(file_path), ...)
    task_runner.schedule(_process_video_file(new_job_id, str(file_path), ...))
```

New error code: `UPLOAD_FILE_MISSING` (for the edge case where the file was
manually deleted).

### Cleanup

The uploaded file is cleaned up when:
- The task is deleted (`cancel_or_delete_task`, `batch_delete_endpoint`)
- The task is cancelled (existing `finally` block)
- The task completes successfully (existing `finally` block)

Failed tasks keep the file until the user deletes the task.

---

## R5 — Stable error codes for progress messages

### Error codes by stage

| Stage where failure occurs | Error code |
|-----------------------------|-----------|
| `get_video_info` / subtitle extraction / audio download | `VIDEO_FETCH_FAILED` |
| `transcribe_audio` | `TRANSCRIPTION_FAILED` |
| `generate_notes` | `NOTE_GENERATION_FAILED` |
| Task recovery (existing) | `TASK_RECOVERY_UNSUPPORTED_URL`, `TASK_RECOVERY_INPUT_INVALID` |

### Implementation

Wrap each stage in a try/except inside `_process_video_url` /
`_process_video_file`:

```python
try:
    video_info = await asyncio.to_thread(get_video_info, ...)
except Exception as e:
    logger.exception(...)
    await update_progress(job_id, TaskStage.failed, 0.0, "VIDEO_FETCH_FAILED")
    return
```

Keep the outer `except Exception` as a last resort with a generic
`PROCESSING_FAILED` code.

### Frontend

Add to `TASK_MESSAGE_ERROR_CODES` in `client.ts`:
```
VIDEO_FETCH_FAILED, TRANSCRIPTION_FAILED, NOTE_GENERATION_FAILED,
PROCESSING_FAILED, UPLOAD_FILE_MISSING
```

Add i18n keys in `en.json` and `zh-CN.json`:
```json
"videoFetchFailed": "Failed to fetch video information",
"transcriptionFailed": "Audio transcription failed",
"noteGenerationFailed": "Note generation failed",
"processingFailed": "Processing failed",
"uploadFileMissing": "The uploaded file is no longer available. Please re-upload."
```

Note: `processingFailed` already exists in `en.json` under `errors` but with
a different key path. The existing `errors.processingFailed` = "Processing
failed" can be reused. Verify no duplicate.

---

## Compatibility

- **DB**: R3/R6 requires persisting title/thumbnail after task creation.
  `title` and `thumbnail_url` columns already exist. No migration needed.
- **API**: `ProcessResponse.title` and `.thumbnail_url` may now be empty
  strings. Frontend must tolerate this (already nullable in `TaskListItem`).
- **Frontend**: `translateTaskMessage` set is additive; existing messages
  still work.

## Rollback

All changes are backward-compatible at the DB level. Rolling back means
reverting the code; no data migration is needed.