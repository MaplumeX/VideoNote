# Logging Guidelines

> How logging is done in this project.

---

## Overview

- **Library**: Python stdlib `logging`
- **Logger per module**: `logger = logging.getLogger(__name__)`
- **Configuration**: No custom handler/formatter setup — uvicorn configures root logger
- **No structured logging**: Plain text, no JSON formatter

---

## Log Levels

| Level | When to use | Example |
|-------|-------------|---------|
| `logger.info()` | Normal operational milestones | `"Audio file is 120MB, splitting"`, `"Extracting audio: video.mp4 -> audio.wav"` |
| `logger.warning()` | Recoverable issues, degraded operation | `"Subtitle extraction failed for {url}: {e}"`, `"Failed to get video title for {url}: {e}"` |
| `logger.exception()` | Unrecoverable errors with full traceback | `"Task {job_id} failed: {e}"` in top-level catch blocks |

- No `logger.debug()` usage currently — info-level is the baseline for operational visibility
- `logger.error()` not used — `logger.exception()` is preferred for errors (includes traceback)

---

## What to Log

- Task lifecycle events: stage transitions, progress updates (in service layer, not every SSE tick)
- External API call decisions: file splitting due to size, subtitle not found (triggers fallback)
- Failures in external tool calls: yt-dlp errors, ffmpeg failures, ASR/LLM API errors
- Authentication anomalies: token reuse detection, refresh failures (implicit via exception handling)

---

## What NOT to Log

- **API keys** — never log `ASR_API_KEY`, `LLM_API_KEY`, or user-provided keys
- **User passwords** — even hashed, don't log them
- **Full request bodies** — video URLs may be sensitive; transcript text can be large
- **SSE tick data** — every-second progress updates flood logs; log stage transitions only

---

## Pattern: Service-layer logging

Each service module creates its own logger and logs at the point of decision:

```python
# services/transcribe.py
logger = logging.getLogger(__name__)

def transcribe_audio(audio_path, ...):
    if audio_size > max_size:
        logger.info(f"Audio file {audio_path} is {size_mb:.1f}MB, splitting")
    ...
```

```python
# services/subtitle.py
logger = logging.getLogger(__name__)

def extract_subtitles(url, ...):
    ...
    logger.info(f"No subtitles found for {url}")
    ...
    logger.warning(f"Subtitle extraction failed for {url}: {e}")
```

---

## Pattern: Route-level error logging

In route handler catch-all blocks, use `logger.exception()` to capture full traceback:

```python
# api/routes.py — _process_video_url
except Exception as e:
    logger.exception(f"Task {job_id} failed: {e}")
    await update_progress(job_id, TaskStage.failed, 0.0, f"Error: {str(e)}")
```

This ensures both the traceback and the user-facing error message are captured.
