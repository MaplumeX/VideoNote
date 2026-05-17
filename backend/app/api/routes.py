"""FastAPI routes for VideoNote."""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from urllib.parse import urlparse

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from app.config import MAX_UPLOAD_SIZE_MB, REDIS_URL, UPLOAD_DIR
from app.schemas import NoteResponse, TaskStage, VideoRequest
from app.services.subtitle import detect_video_platform

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_redis_settings() -> RedisSettings:
    parsed = urlparse(REDIS_URL)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


async def _get_arq_pool():
    return await create_pool(_get_redis_settings())


@router.post("/process")
async def process_video(request: VideoRequest):
    """Submit a video URL for processing. Returns a job_id."""
    url = str(request.url)
    platform = detect_video_platform(url)
    if platform == "unknown":
        raise HTTPException(
            status_code=422,
            detail="Unsupported video platform. Only YouTube and Bilibili URLs are supported.",
        )

    job_id = str(uuid.uuid4())

    # Initialize task in Redis
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.hset(
            f"videonote:task:{job_id}",
            mapping={
                "progress": json.dumps({
                    "stage": TaskStage.pending.value,
                    "progress": 0.0,
                    "message": "Queued",
                }),
            },
        )
    finally:
        await r.aclose()

    # Enqueue ARQ task
    pool = await _get_arq_pool()
    await pool.enqueue_job("process_video_url", job_id, url)

    return {"job_id": job_id}


ALLOWED_VIDEO_TYPES = {
    "video/mp4", "video/webm", "video/x-matroska", "video/quicktime",
    "video/x-msvideo", "video/x-flv", "video/mpeg", "video/3gpp",
    "video/x-ms-wmv",
}

ALLOWED_EXTENSIONS = {
    ".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv", ".mpeg", ".3gp", ".wmv",
}


@router.post("/upload")
async def upload_video(file: UploadFile):
    """Upload a local video file for processing. Returns a job_id."""
    # Validate content type or extension
    content_type = file.content_type or ""
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if (
        content_type not in ALLOWED_VIDEO_TYPES
        and ext not in ALLOWED_EXTENSIONS
    ):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type or ext}. Only video files are accepted.",
        )

    job_id = str(uuid.uuid4())

    # Sanitize filename to prevent path traversal
    safe_name = Path(file.filename).name if file.filename else "upload"
    safe_name = safe_name.replace("..", "")
    if not safe_name:
        safe_name = "upload"

    # Read file in chunks to check size
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file_path = UPLOAD_DIR / f"{job_id}_{safe_name}"

    size = 0
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                file_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Max size: {MAX_UPLOAD_SIZE_MB}MB",
                )
            f.write(chunk)

    # Initialize task in Redis
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.hset(
            f"videonote:task:{job_id}",
            mapping={
                "progress": json.dumps({
                    "stage": TaskStage.pending.value,
                    "progress": 0.0,
                    "message": "Uploaded, queued",
                }),
            },
        )
    finally:
        await r.aclose()

    # Enqueue ARQ task
    pool = await _get_arq_pool()
    await pool.enqueue_job("process_video_file", job_id, str(file_path))

    return {"job_id": job_id}


@router.get("/tasks/{job_id}/progress")
async def task_progress(job_id: str):
    """SSE endpoint for real-time task progress updates."""
    async def event_generator():
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        try:
            while True:
                raw = await r.hget(f"videonote:task:{job_id}", "progress")
                if raw:
                    data = json.loads(raw)
                    yield {
                        "event": "progress",
                        "data": json.dumps(data),
                    }
                    if data.get("stage") in (
                        TaskStage.complete.value,
                        TaskStage.failed.value,
                    ):
                        # Send final result if available
                        result_raw = await r.hget(
                            f"videonote:task:{job_id}", "result"
                        )
                        if result_raw:
                            yield {
                                "event": "complete",
                                "data": result_raw,
                            }
                        break
                await asyncio.sleep(1)
        finally:
            await r.aclose()

    return EventSourceResponse(event_generator())


@router.get("/tasks/{job_id}/result", response_model=NoteResponse)
async def task_result(job_id: str):
    """Get the final note result for a completed task."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        raw = await r.hget(f"videonote:task:{job_id}", "result")
        if not raw:
            # Check if task exists at all
            progress_raw = await r.hget(
                f"videonote:task:{job_id}", "progress"
            )
            if not progress_raw:
                raise HTTPException(status_code=404, detail="Task not found")
            progress = json.loads(progress_raw)
            if progress.get("stage") == TaskStage.failed.value:
                raise HTTPException(
                    status_code=500,
                    detail=progress.get("message", "Task failed"),
                )
            raise HTTPException(status_code=202, detail="Task still processing")

        result = json.loads(raw)
        return NoteResponse(
            job_id=job_id,
            markdown=result.get("markdown", ""),
            title=result.get("title"),
        )
    finally:
        await r.aclose()
