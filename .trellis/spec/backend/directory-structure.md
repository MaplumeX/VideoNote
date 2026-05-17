# Directory Structure

> How backend code is organized in this project.

---

## Directory Layout

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, CORS, lifespan, route includes
│   ├── config.py            # Settings via pydantic-settings + dotenv
│   ├── schemas.py           # Pydantic request/response models
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py        # REST + SSE endpoints
│   └── services/
│       ├── __init__.py
│       ├── subtitle.py      # yt-dlp subtitle extraction
│       ├── audio.py         # ffmpeg audio extraction
│       ├── transcribe.py    # OpenAI Whisper API
│       └── note_gen.py     # LLM note generation
├── worker.py                # ARQ async task worker
├── pyproject.toml           # Dependencies (managed by uv)
└── tests/
    └── __init__.py
```

---

## Module Organization

- **`app/main.py`**: App factory, CORS middleware, route mounting. No business logic.
- **`app/config.py`**: Single `Settings` class with `model_config = SettingsConfigDict(env_file=".env")`. All env vars centralized here.
- **`app/schemas.py`**: All Pydantic models in one file. Group by domain (request, response, internal).
- **`app/api/routes.py`**: All HTTP endpoints. Thin handlers — delegate to services/worker.
- **`app/services/`**: One file per external integration (yt-dlp, ffmpeg, Whisper, LLM). Each service is stateless and async-compatible.
- **`worker.py`**: ARQ worker with `WorkerSettings` class. Task functions at module level.

---

## Naming Conventions

- Files: `snake_case.py`
- Pydantic models: `PascalCase` (e.g., `VideoRequest`, `TaskProgress`)
- Service functions: `verb_noun` (e.g., `extract_subtitles`, `extract_audio`)
- ARQ task functions: `verb_noun` (e.g., `process_video_url`, `process_video_file`)
- Config fields: `UPPER_SNAKE_CASE` (env var names)

---

## Adding a New Service

1. Create `app/services/<name>.py` with async functions
2. Add any new env vars to `app/config.py`
3. Add any new Pydantic models to `app/schemas.py`
4. Import and call from `worker.py` or `app/api/routes.py`
