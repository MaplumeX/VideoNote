# Single image: builds frontend + backend into one runtime image.
# FastAPI serves the bundled SPA so no nginx/supervisord is needed.

# ---- Stage 1: build frontend ----
FROM node:22-alpine AS frontend-builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---- Stage 2: install backend deps ----
FROM python:3.11-slim AS backend-builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# ---- Stage 3: runtime ----
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=backend-builder /app/.venv /app/.venv
COPY backend/app/ /app/app/
COPY --from=frontend-builder /build/dist /app/static

ENV PATH="/app/.venv/bin:$PATH"
ENV UPLOAD_DIR=/data/videonote
ENV FRONTEND_STATIC_DIR=/app/static
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]