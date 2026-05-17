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


## Session 4: Support SiliconFlow as ASR Provider

**Date**: 2026-05-17
**Task**: Support SiliconFlow as ASR Provider
**Branch**: `feat/siliconflow-transcription`

### Summary

Added ASR_PROVIDER env var (openai/siliconflow). SiliconFlow mode sends only file+model params, uses 50MB limit, returns plain text. OpenAI mode unchanged.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6ca7a27` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: Add i18n internationalization support (en + zh-CN)

**Date**: 2026-05-17
**Task**: Add i18n internationalization support (en + zh-CN)
**Branch**: `feat/add-i18n`

### Summary

为 VideoNote 添加 i18n 支持：前端 react-i18next + 浏览器语言检测 + Header 切换按钮；后端 language 参数 + prompt 模板按语言组织。初始支持 en/zh-CN。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `85cb9be` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
