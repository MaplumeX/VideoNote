# Implement: fix core note pipeline bugs

## Ordered checklist

### Phase A — Backend service layer

- [ ] **A1** `app/services/subtitle.py`: add `_srt_to_transcript(raw: str) -> str | None`
  parsing SRT/VTT into `[HH:MM:SS](#t=SECONDS) text` lines.
- [ ] **A2** `app/services/subtitle.py`: call `_srt_to_transcript()` inside
  `extract_subtitles()` and `_download_and_read_subtitle()` before returning,
  so the transcript is in `#t=`-link format. Return `None` when the converter
  yields no valid cues.

### Phase B — Backend route layer

- [ ] **B1** `app/api/routes.py`: add `_asr_language(note_lang: str) -> str`
  helper (`zh-CN` → `zh`, else `en`).
- [ ] **B2** `app/api/routes.py`: pass `language=_asr_language(language)` to
  both `transcribe_audio` calls in `_process_video_url` and
  `_process_video_file`.
- [ ] **B3** `app/services/transcribe.py`: change default `language` from
  `"zh"` to `"en"` (safety net; callers always pass a value now).
- [ ] **B4** `app/db.py`: add `update_task_meta(job_id, title, thumbnail_url)`
  to persist title/thumbnail after background fetch.
- [ ] **B5** `app/api/routes.py` — `process_video`: remove synchronous
  `get_video_info` + `download_thumbnail`. Create task with
  `title=None, thumbnail_url=None`, schedule background job, return
  `ProcessResponse(title="", thumbnail_url="", platform=platform)`.
- [ ] **B6** `app/api/routes.py` — `_process_video_url`: move cookie
  resolution, `get_video_info`, `download_thumbnail` to the start of the
  background job. Call `update_task_meta()` after fetching. Wrap stage in
  try/except → `VIDEO_FETCH_FAILED`.
- [ ] **B7** `app/api/routes.py` — `retry_task`: same defer pattern as B5.
- [ ] **B8** `app/api/routes.py` — `_process_video_url` / `_process_video_file`:
  wrap transcribe stage in try/except → `TRANSCRIPTION_FAILED`; wrap
  `generate_notes` in try/except → `NOTE_GENERATION_FAILED`. Keep outer
  `except Exception` → `PROCESSING_FAILED`.
- [ ] **B9** `app/api/routes.py` — `_process_video_file` `finally`: remove
  `TaskStage.failed` from the file-deletion condition (keep file for retry).
- [ ] **B10** `app/api/routes.py` — `retry_task`: add `source_type == "upload"`
  branch that reuses `input_file_path` when the file still exists. Raise
  `UPLOAD_FILE_MISSING` (422) if the file is gone. Remove the
  `ONLY_URL_CAN_RETRY` guard.

### Phase C — Frontend

- [ ] **C1** `frontend/src/api/client.ts`: extend `TASK_MESSAGE_ERROR_CODES`
  with `VIDEO_FETCH_FAILED`, `TRANSCRIPTION_FAILED`,
  `NOTE_GENERATION_FAILED`, `PROCESSING_FAILED`, `UPLOAD_FILE_MISSING`.
- [ ] **C2** `frontend/src/i18n/locales/en.json`: add i18n keys for the new
  error codes under `errors.*` (camelCase).
- [ ] **C3** `frontend/src/i18n/locales/zh-CN.json`: add Chinese translations.
- [ ] **C4** Verify frontend `submitUrl` caller tolerates empty
  `title`/`thumbnail_url` (they are already `""` by default in
  `ProcessResponse`; confirm the UI doesn't break on empty title).

### Phase D — Tests

- [ ] **D1** Add test for `_srt_to_transcript`: SRT input → `#t=` links;
  VTT input → `#t=` links; malformed input → `None`.
- [ ] **D2** Add test that `transcribe_audio` receives the user's language
  (mock the OpenAI client, verify `language=` kwarg).
- [ ] **D3** Add test that `process_video` creates the task and returns
  without calling `get_video_info` (mock `task_runner.schedule` and
  `get_video_info`).
- [ ] **D4** Add test that a failed upload task retains `input_file_path`
  and the file on disk.
- [ ] **D5** Add test that `retry_task` works for upload tasks.
- [ ] **D6** Add test that failed-task `message` is a stable error code,
  not raw exception text.

## Validation commands

```bash
cd backend && uv run pytest
cd backend && uv run ruff check .
cd frontend && npm run lint
cd frontend && npm run build
```

## Risky files / rollback points

- `app/api/routes.py` — most changes here; if something breaks, revert this
  file to restore the old pipeline.
- `app/services/subtitle.py` — SRT parser is new code; if it fails on edge
  cases, `extract_subtitles` returns `None` and the pipeline falls back to
  ASR (safe degradation).

## Review gates

- After Phase A+B: run backend tests + ruff.
- After Phase C: run frontend lint + build.
- After Phase D: full test suite green.