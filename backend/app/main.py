import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth_routes import router as auth_router
from app.api.cookie_routes import router as cookie_router
from app.api.note_routes import router as note_router
from app.api.routes import recover_incomplete_tasks, router
from app.db import cleanup_failed_task_files, cleanup_old_terminal_tasks, close_db, init_db
from app.task_runner import task_runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger(__name__)
    await init_db()
    await recover_incomplete_tasks()
    cleaned = await cleanup_failed_task_files()
    if cleaned:
        logger.info("Cleaned up %d failed task files", cleaned)
    cleaned_tasks = await cleanup_old_terminal_tasks()
    if cleaned_tasks:
        logger.info("Cleaned up %d old terminal tasks", cleaned_tasks)
    try:
        yield
    finally:
        await task_runner.shutdown()
        await close_db()


app = FastAPI(title="VideoNote", version="1.0.0", lifespan=lifespan)

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(cookie_router, prefix="/api")
app.include_router(note_router, prefix="/api")
app.include_router(router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve bundled frontend (single-image deployment). When the dist directory
# exists, FastAPI serves Vite assets and falls back to index.html for the SPA.
frontend_dist = Path(os.getenv("FRONTEND_STATIC_DIR", "/app/static"))
if frontend_dist.is_dir():
    _assets = frontend_dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Return a root-level static file (e.g. favicon.ico) if it exists.
        candidate = frontend_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = frontend_dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return {"detail": "Not Found"}
