# Directory Structure

> How backend code is organized in this project.

---

## Directory Layout

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, CORS, lifespan, route includes
│   ├── config.py            # Module-level env vars via dotenv
│   ├── schemas.py           # Pydantic request/response models
│   ├── auth.py              # JWT creation, password hashing, Depends injection
│   ├── crypto.py            # Fernet encryption for API keys
│   ├── db.py                # SQLite (aiosqlite) operations, schema init
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py        # REST + SSE endpoints (video processing, settings)
│   │   └── auth_routes.py   # Auth endpoints (register, login, refresh, logout)
│   └── services/
│       ├── __init__.py
│       ├── subtitle.py      # yt-dlp subtitle extraction
│       ├── audio.py         # ffmpeg audio extraction + yt-dlp audio download
│       ├── transcribe.py    # OpenAI Whisper / SiliconFlow ASR
│       └── note_gen.py      # LLM note generation
├── pyproject.toml           # Dependencies (managed by uv), ruff/pytest config
└── tests/
    └── __init__.py
```

---

## Module Organization

- **`app/main.py`**: App factory, CORS middleware, route mounting. No business logic.
- **`app/config.py`**: Module-level constants loaded from env via `os.getenv()`. No `pydantic-settings` class — flat module-level variables.
- **`app/schemas.py`**: All Pydantic models in one file. Group by domain (video, auth, settings).
- **`app/auth.py`**: JWT creation (`create_access_token`), password hashing (`bcrypt` via `asyncio.to_thread`), `get_current_user` dependency. Uses `Annotated` type alias pattern.
- **`app/crypto.py`**: Fernet symmetric encryption derived from `SECRET_KEY`. Used to encrypt/decrypt user API keys stored in DB.
- **`app/db.py`**: All SQLite operations. Schema creation, task CRUD, user CRUD, refresh token CRUD, provider config CRUD. Raw SQL with `aiosqlite`.
- **`app/api/routes.py`**: Video processing endpoints + provider/settings endpoints. Thin handlers — delegate to services. Task execution via `asyncio.create_task`.
- **`app/api/auth_routes.py`**: Auth-only endpoints with `/auth` prefix. Cookie-based refresh tokens.
- **`app/services/`**: One file per external integration (yt-dlp, ffmpeg, Whisper, LLM). Each service is stateless. Sync functions called via `asyncio.to_thread()` from route handlers.

---

## Naming Conventions

- Files: `snake_case.py`
- Pydantic models: `PascalCase` (e.g., `VideoRequest`, `TaskProgress`)
- Service functions: `verb_noun` (e.g., `extract_subtitles`, `generate_notes`)
- Config fields: `UPPER_SNAKE_CASE` (env var names)
- DB tables: `snake_case` plural (e.g., `tasks`, `users`, `refresh_tokens`)

---

## Adding a New Service

1. Create `app/services/<name>.py` with sync functions (external APIs are sync)
2. Add any new env vars to `app/config.py`
3. Add any new Pydantic models to `app/schemas.py`
4. Add DB operations to `app/db.py` if new tables/columns needed
5. Import and call from `app/api/routes.py` via `asyncio.to_thread()`
