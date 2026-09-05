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

---

## Pipeline Package (new core pipeline, C1+)

The core pipeline is being rewritten into `app/pipeline/`. The single source of
truth for its contracts is **`docs/pipeline-contract.md`** — read it before
touching any pipeline code.

```
backend/app/pipeline/
├── state.py        # TaskStatus/PipelinePhase enums, transition table, Checkpoint, resume_point
├── errors.py       # ErrorCode enum, PipelineError (sanitized at construction), sanitize_detail
├── progress.py     # ProgressEvent, ProgressPublisher protocol, PhaseProgressTracker
└── stages/
    └── base.py     # Stage/StageContext/StageResult protocols, ArtifactStore, ProviderConfig
```

### Scenario: Implementing a pipeline stage (C2/C3)

#### 1. Scope / Trigger
- Trigger: any new module under `app/pipeline/stages/`.

#### 2. Signatures
- `class Stage(Protocol)`: `phase: ClassVar[PipelinePhase]`, `async def run(ctx: StageContext, *, resume: bool) -> StageResult`.
- `StageContext` carries `job_id`, `language`, `provider: ProviderConfig`, `artifacts: ArtifactStore`, `progress: ProgressPublisher`, `register_cancel`.
- Stage outputs go in `StageResult.outputs: dict[ArtifactKind, object]` — the orchestrator (C4) persists them, stages never write the DB directly.

#### 3. Contracts
- Artifacts are read/written via `ArtifactStore` (kinds: `video_meta | subtitle | transcript | notes_draft`).
- Errors raised to the orchestrator must be `PipelineError(code, detail=...)` — `detail` is sanitized inside the constructor; never hand-build error message strings.
- Progress is reported as `phase + fraction ∈ [0,1]` via `ctx.progress.publish(...)`; `PhaseProgressTracker` enforces monotonicity per phase.
- Cancellation: register subprocess/task cancel handles via `ctx.register_cancel`; no `threading.Event` anywhere in pipeline code.

#### 4. Validation & Error Matrix
- Illegal phase transition -> `InvalidTransitionError` (state machine is authoritative).
- `sanitize_detail` strips `sk-*` keys, `Bearer` tokens, cookie headers; truncates to 200 chars.

#### 5. Good/Base/Bad Cases
- Good: stage raises `PipelineError(ErrorCode.TRANSCRIPTION_FAILED, detail=str(e))`.
- Base: stage returns `StageResult` with outputs; orchestrator checkpoints.
- Bad: stage writes SQLite directly or formats `"CODE: detail"` strings itself.

#### 6. Tests Required
- Stage tests use injected fake clients (no network) and must assert real behavior, not mock echoes.
- Subprocess-based stages need a real (small) fixture to prove kill-on-cancel.

#### 7. Wrong vs Correct

```python
# WRONG — hand-built error string, unsanitized
raise RuntimeError(f"TRANSCRIPTION_FAILED: {e}")

# CORRECT — structured, sanitized at construction
raise PipelineError(ErrorCode.TRANSCRIPTION_FAILED, detail=str(e), cause=e) from e
```

The legacy `app/services/` pipeline remains the live path until C4 switches
over; do not modify it while `app/pipeline/` is under construction.
