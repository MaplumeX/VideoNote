# Journal - Maplume (Part 1)

> AI development session journal
> Started: 2026-05-17

---



## Session 1: VideoNote MVP: AI video note summarizer (backend + frontend)

**Date**: 2026-05-17
**Task**: VideoNote MVP: AI video note summarizer (backend + frontend)
**Branch**: `main`

### Summary

Built VideoNote MVP — a web app that takes video URLs (YouTube/Bilibili) or local files, extracts content (subtitle-first with ASR fallback via OpenAI Whisper), and generates structured Markdown notes with timestamps via LLM. Stack: FastAPI + ARQ (Redis) + yt-dlp + ffmpeg backend, Vite + React 19 + Tailwind + react-markdown frontend, SSE for progress. Quality check fixed 8 issues (path traversal, file type validation, URL platform check, React render-during-setState, SSE stale closure, props spread, video title extraction). Updated 8 spec files with project conventions.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0f7a55a` | (see git log) |
| `e33562b` | (see git log) |
| `60411d1` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: Remove Redis: replace ARQ+Redis with SQLite+asyncio

**Date**: 2026-05-17
**Task**: Remove Redis: replace ARQ+Redis with SQLite+asyncio
**Branch**: `feat/remove-redis`

### Summary

Removed Redis/ARQ dependencies. Task queue replaced by asyncio.create_task in-process. Task state migrated from Redis Hash to SQLite (WAL mode, aiosqlite). Sync blocking calls wrapped with asyncio.to_thread(). File cleanup moved to finally block. Deleted worker.py.


## Session 3: Support custom ASR/LLM providers

**Date**: 2026-05-17
**Task**: Support custom ASR/LLM providers
**Branch**: `feat/llm-provider`

### Summary

Add independent ASR_API_KEY/ASR_API_BASE/ASR_MODEL and LLM_API_KEY env vars with backward-compatible fallback to OPENAI_API_KEY/OpenAI defaults

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `bb993fc` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
