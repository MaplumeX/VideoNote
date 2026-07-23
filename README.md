# VideoNote

> Turn any video into structured Markdown notes — with clickable timestamps, WYSIWYG editing, and full organization.

[English](README.md) · [简体中文](README.zh-CN.md)

VideoNote takes a video URL (YouTube / Bilibili) or an uploaded video file, extracts its subtitles (falling back to ASR transcription when no subtitles exist), and uses an LLM to generate well-structured Markdown notes with clickable timestamp links. Notes are editable in a WYSIWYG Markdown editor and can be organized with folders, tags, favorites, and search.

---

## Features

- **Two input sources** — submit a video URL (YouTube / Bilibili) or upload a local video file.
- **Smart transcript pipeline** — prefer existing subtitles; fall back to audio extraction (`ffmpeg`) + ASR transcription when none are available.
- **LLM note generation** — produces structured Markdown with proper headings, bullets, per-section summaries, and clickable `[HH:MM:SS](#t=SECONDS)` timestamps.
- **Real-time progress** — server-sent events (SSE) stream stage and progress to the UI.
- **WYSIWYG editor** — [Milkdown](https://milkdown.dev/) editor with GFM, KaTeX math, Mermaid diagrams, and Prism code highlighting.
- **Note organization** — folder tree, tags, favorites, batch operations, full-text search, and pagination.
- **Per-user provider config** — configure ASR and LLM providers independently (OpenAI, SiliconFlow, DeepSeek, or any OpenAI-compatible endpoint). API keys are encrypted at rest.
- **Cookie management** — per-user cookies for YouTube / Bilibili to access members-only or region-restricted content.
- **Auth** — JWT-based user accounts with refresh tokens and bcrypt password hashing.
- **Bilingual UI** — English and 简体中文, auto-detected.
- **Single-image deploy** — the Vite SPA is bundled into the FastAPI runtime image; no nginx or supervisord needed.

## Tech Stack

| Layer    | Stack                                                                                          |
| -------- | ---------------------------------------------------------------------------------------------- |
| Backend  | Python 3.11 · FastAPI · asyncio · aiosqlite · yt-dlp · ffmpeg · OpenAI SDK · PyJWT · bcrypt    |
| Frontend | React 19 · Vite · TypeScript · TailwindCSS v4 · shadcn/ui · Milkdown · i18next · React Router |
| Infra    | Single multi-stage Docker image published to GHCR · docker-compose                             |

## Quick Start (Docker)

The image is published to the GitHub Container Registry:

```bash
docker pull ghcr.io/maplumex/videonote:latest
```

### One-line deploy

Fetch the compose file and an env template, generate a stable secret, then launch — all from a shell:

```bash
# 1. Download docker-compose.yml and .env template
curl -fsSL https://raw.githubusercontent.com/MaplumeX/VideoNote/main/docker-compose.yml -o docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/MaplumeX/VideoNote/main/.env.example -o .env

# 2. Set required values: deployed origin + a stable secret key
echo "FRONTEND_URL=http://localhost" >> .env
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env

# 3. (Optional) Provide an OpenAI key, or configure per-user providers in the UI later
echo "OPENAI_API_KEY=sk-..." >> .env

# 4. Launch
docker compose up -d
```

Then open <http://localhost:8965>, register an account, and configure your ASR / LLM providers in **Settings**.

### Manual setup

1. Copy `.env.example` to `.env` and fill in your keys:

   ```bash
   cp .env.example .env
   ```

   Required for Docker deployments:

   ```dotenv
   # Set to your deployed origin (e.g. https://note.example.com)
   FRONTEND_URL=http://localhost

   # A STABLE secret key — auto-generated keys are lost on container restart,
   # which makes encrypted API keys unrecoverable.
   SECRET_KEY=<your-stable-secret-key>
   ```

2. Start with `docker compose`:

   ```bash
   docker compose up -d
   ```

3. Open <http://localhost:8965>, register an account, and configure your ASR / LLM providers in **Settings**.

### Environment Variables

| Variable                       | Description                                                        | Default                        |
| ------------------------------ | ------------------------------------------------------------------ | ------------------------------ |
| `OPENAI_API_KEY`               | Fallback key for ASR/LLM when per-user config is absent            | —                              |
| `ASR_PROVIDER`                 | `openai` or `siliconflow`                                          | `openai`                       |
| `ASR_API_BASE`                 | ASR endpoint                                                       | `https://api.openai.com/v1`    |
| `ASR_MODEL`                    | ASR model (e.g. `whisper-1`, `FunAudioLLM/SenseVoiceSmall`)        | `whisper-1`                    |
| `LLM_API_BASE`                 | LLM endpoint                                                       | `https://api.openai.com/v1`    |
| `LLM_MODEL`                    | LLM model (e.g. `gpt-4o`, `deepseek-chat`)                         | `gpt-4o`                       |
| `YT_DLP_PROXY`                 | Proxy for yt-dlp (accessing YouTube etc.)                          | —                              |
| `YT_DLP_COOKIES_FROM_BROWSER`  | Load yt-dlp cookies from a browser profile (e.g. `chrome`)         | —                              |
| `YT_DLP_COOKIES_FILE`          | Path to a Netscape `cookies.txt` file                               | —                              |
| `UPLOAD_DIR`                   | Directory for uploaded files and thumbnails                        | `/tmp/videonote_uploads`        |
| `MAX_UPLOAD_SIZE_MB`            | Max upload size                                                    | `500`                          |
| `SECRET_KEY`                   | JWT signing key (**must be set explicitly in Docker**)             | auto-generated                 |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | Access token lifetime                                              | `15`                           |
| `REFRESH_TOKEN_EXPIRE_DAYS`    | Refresh token lifetime                                             | `7`                            |
| `FRONTEND_URL`                 | CORS allowed origin (**required for Docker**)                      | `http://localhost:5173`        |
| `FRONTEND_STATIC_DIR`          | Path to bundled frontend assets (set by the Docker image)         | `/app/static`                   |

See [`.env.example`](.env.example) for the full, commented configuration.

## Local Development

### Prerequisites

- Python 3.11+ with [`uv`](https://docs.astral.sh/uv/)
- Node.js 22+
- `ffmpeg` installed and on `PATH`

### Backend

```bash
cd backend
uv sync
cp ../.env.example ../.env   # then edit .env
uv run uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm ci
npm run dev    # http://localhost:5173
```

When running the frontend separately from the backend, set `FRONTEND_URL=http://localhost:5173` in `.env` so CORS allows the dev server.

### Tests & Lint

```bash
# Backend
cd backend
uv run pytest
uv run ruff check .

# Frontend
cd frontend
npm run lint
npm run build
```

## How It Works

```
URL / file
   │
   ├─ URL ──► yt-dlp ──► fetch video info & thumbnail
   │                       │
   │                       └─► try subtitle extraction
   │                              │
   │                              └─ no subtitles? ─► download audio ─► ASR transcription
   │
   └─ File ──► ffmpeg ──► extract audio ─► ASR transcription
                                                  │
                                                  └─► LLM note generation ─► Markdown note
                                                                                     │
                                                                                     └─► stored, editable
```

Progress for every stage is streamed to the client via SSE.

## License

This project is licensed under the MIT License.