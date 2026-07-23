# fix: core note pipeline bugs

## Goal

Fix six bugs in the core video-to-note pipeline that cause incorrect output,
wasted work, unrecoverable failures, and poor submission UX.

## Background

The core pipeline is: submit URL/file → fetch video info → extract subtitles
or ASR transcribe → LLM generates Markdown notes → SSE streams progress.

Several bugs degrade correctness and UX:

1. **Subtitle timestamps silently lost** — `routes.py` detects timestamps via
   `"#t=" in transcript`, but `subtitle.py` returns raw SRT/VTT text (no
   `#t=`). So the subtitle path always selects `_PROMPTS_WITHOUT_TIMESTAMPS`,
   telling the LLM *not* to add timestamps. README's headline feature
   (clickable timestamps) is broken for the subtitle path.

2. **Transcription language hardcoded to Chinese** — `transcribe_audio()`
   defaults `language="zh"`. `_process_video_url` / `_process_video_file`
   never pass the user's selected language. Whisper is forced to interpret
   English (and other) audio as Chinese, degrading accuracy.

3. **`get_video_info` called twice** — `process_video` / `retry_task` call
   `get_video_info` synchronously (for title/thumbnail), then schedule
   `_process_video_url` which calls it again. yt-dlp info extraction can
   take 10–30s; doing it twice doubles the latency.

4. **Failed upload tasks are unrecoverable** — `_process_video_file` deletes
   the uploaded file in `finally` when stage is `failed`, and `retry_task`
   rejects non-URL tasks (`ONLY_URL_CAN_RETRY`). Users must re-upload
   large files (up to 500 MB) after any transient failure.

5. **Raw exception text leaked via SSE** — `_process_video_url` /
   `_process_video_file` write `f"Error: {str(e)}"` as the progress message.
   This may expose internal paths, key fragments, or stack details to the
   frontend. `recover_incomplete_tasks` writes the error *code*
   `TASK_RECOVERY_UNSUPPORTED_URL` as a message string (works only because
   `translateTaskMessage` has a hardcoded set).

6. **Submission blocks on yt-dlp** — `POST /process` runs `get_video_info` +
   `download_thumbnail` synchronously before returning. The user waits
   10–30s with no job_id, no SSE connection, and no way to cancel or
   recover if they navigate away.

## Requirements

### R1 — Subtitle path preserves timestamps

- `subtitle.py` must convert SRT/VTT subtitle text into the same
  `[HH:MM:SS](#t=SECONDS) text` format that the ASR path produces, so the
  existing `has_timestamps` detection and the "with-timestamps" LLM prompt
  work correctly.
- Must handle both SRT (`,000` ms separator) and VTT (`.000` ms separator)
  timestamp formats.
- Empty/malformed subtitle content must not crash; return `None` so the
  pipeline falls back to ASR.

### R2 — Transcription language follows user selection

- `_process_video_url` and `_process_video_file` must pass the user-selected
  language (mapped from note-language codes to Whisper language codes:
  `zh-CN` → `zh`, `en` → `en`) to `transcribe_audio`.
- `transcribe_audio` must accept and use the passed language instead of
  defaulting to `"zh"`.

### R3 — `get_video_info` called once

- `process_video` and `retry_task` must not call `get_video_info`
  synchronously before scheduling. The background job must call it once
  and update the task row with title/thumbnail.

### R4 — Failed upload tasks are retryable

- `_process_video_file` must not delete the uploaded file when the task
  fails. File cleanup happens only on task deletion or cancellation.
- `retry_task` must support `source_type="upload"` tasks when the input
  file still exists, creating a new task that reuses the same file path.

### R5 — Progress messages use stable error codes

- `_process_video_url` / `_process_video_file` must write a stable
  error-code string (not raw `str(e)`) as the progress message on failure.
- New error codes: `VIDEO_FETCH_FAILED`, `TRANSCRIPTION_FAILED`,
  `NOTE_GENERATION_FAILED` (mapped from the processing stage that failed).
- Frontend i18n must add translations for these codes.
- Raw exception text stays in server logs only.

### R6 — Submit returns job_id immediately

- `POST /process` must create the task and return `job_id` + `platform`
  immediately, without waiting for `get_video_info`.
- `get_video_info` + `download_thumbnail` run inside the background job;
  title and thumbnail are written to the task row and visible via SSE / task
  list once fetched.
- `ProcessResponse.title` and `ProcessResponse.thumbnail_url` may be empty
  at submission time; the frontend must tolerate this and display them when
  they arrive via SSE or task-list refresh.
- `retry_task` follows the same pattern.

## Acceptance Criteria

- [ ] R1: A URL with subtitles produces a transcript containing `#t=`
      timestamp links, and the LLM uses the with-timestamps prompt.
- [ ] R2: An English video transcribed via Whisper receives
      `language="en"`; a Chinese video receives `language="zh"`.
- [ ] R3: `get_video_info` is called exactly once per task (verified by
      test or code inspection).
- [ ] R4: A failed upload task's file survives; retrying it creates a new
      task that reuses the file without re-upload.
- [ ] R5: Failed-task `message` contains a stable error code, not raw
      exception text.
- [ ] R6: `POST /process` returns within milliseconds; title/thumbnail
      arrive later via SSE.

## Out of Scope

- `max_tokens=4096` truncation in `note_gen.py` (#7)
- Hardcoded subtitle language list `["en", "zh-Hans", "zh", "ja"]` (#8)
- Frontend loading-skeleton redesign beyond tolerating empty title/thumbnail