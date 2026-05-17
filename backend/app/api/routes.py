"""FastAPI routes for VideoNote."""

import asyncio
import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from app.auth import TokenData, get_current_user
from app.config import MAX_UPLOAD_SIZE_MB, UPLOAD_DIR
from app.db import create_task, get_task, get_user_tasks, set_result, update_progress
from app.schemas import NoteResponse, TaskListItem, TaskStage, VideoRequest
from app.services.audio import download_audio_via_ytdlp, extract_audio
from app.services.note_gen import generate_notes
from app.services.subtitle import detect_video_platform, extract_subtitles, get_video_title
from app.services.transcribe import transcribe_audio

CurrentUser = Annotated[TokenData, Depends(get_current_user)]

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_LANGUAGES = {"en", "zh-CN"}


def _normalize_language(lang: str) -> str:
    """Normalize language code, fallback to 'en' if unsupported."""
    if lang in SUPPORTED_LANGUAGES:
        return lang
    if lang.startswith("zh"):
        return "zh-CN"
    return "en"


async def _process_video_url(job_id: str, url: str, language: str = "en") -> None:
    """Process a video URL: extract subtitles or transcribe, then generate notes."""
    try:
        video_title = await asyncio.to_thread(get_video_title, url)

        await update_progress(
            job_id, TaskStage.extracting_subtitles, 0.1,
            "Extracting subtitles..."
        )

        subtitle_text = await asyncio.to_thread(extract_subtitles, url)

        if subtitle_text:
            transcript = subtitle_text
            await update_progress(
                job_id, TaskStage.extracting_subtitles, 0.5,
                "Subtitles found"
            )
        else:
            await update_progress(
                job_id, TaskStage.downloading, 0.2,
                "No subtitles, downloading audio..."
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                audio_path = await asyncio.to_thread(
                    download_audio_via_ytdlp, url, tmpdir
                )

                await update_progress(
                    job_id, TaskStage.transcribing, 0.4,
                    "Transcribing audio..."
                )
                transcript = await asyncio.to_thread(transcribe_audio, audio_path)

            await update_progress(
                job_id, TaskStage.transcribing, 0.6,
                "Transcription complete"
            )

        await update_progress(
            job_id, TaskStage.generating_notes, 0.7, "Generating notes..."
        )
        markdown = await asyncio.to_thread(
            generate_notes, transcript, video_title=video_title, language=language
        )

        await update_progress(
            job_id, TaskStage.generating_notes, 0.9, "Notes generated"
        )

        await set_result(job_id, markdown, title=video_title)

    except Exception as e:
        logger.exception(f"Task {job_id} failed: {e}")
        await update_progress(
            job_id, TaskStage.failed, 0.0, f"Error: {str(e)}"
        )


async def _process_video_file(job_id: str, file_path: str, language: str = "en") -> None:
    """Process an uploaded video file: extract audio, transcribe, generate notes."""
    try:
        await update_progress(
            job_id, TaskStage.transcribing, 0.1,
            "Extracting audio from video..."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = str(Path(tmpdir) / "audio.wav")
            await asyncio.to_thread(extract_audio, file_path, audio_path)

            await update_progress(
                job_id, TaskStage.transcribing, 0.3,
                "Transcribing audio..."
            )
            transcript = await asyncio.to_thread(transcribe_audio, audio_path)

        await update_progress(
            job_id, TaskStage.transcribing, 0.6, "Transcription complete"
        )

        await update_progress(
            job_id, TaskStage.generating_notes, 0.7, "Generating notes..."
        )
        markdown = await asyncio.to_thread(
            generate_notes, transcript, language=language
        )

        await update_progress(
            job_id, TaskStage.generating_notes, 0.9, "Notes generated"
        )

        await set_result(job_id, markdown)

    except Exception as e:
        logger.exception(f"Task {job_id} failed: {e}")
        await update_progress(
            job_id, TaskStage.failed, 0.0, f"Error: {str(e)}"
        )
    finally:
        Path(file_path).unlink(missing_ok=True)


@router.post("/process")
async def process_video(
    request: VideoRequest,
    user: CurrentUser,
):
    """Submit a video URL for processing. Returns a job_id."""
    url = str(request.url)
    platform = detect_video_platform(url)
    if platform == "unknown":
        raise HTTPException(
            status_code=422,
            detail="Unsupported video platform. Only YouTube and Bilibili URLs are supported.",
        )

    language = _normalize_language(request.language)
    job_id = str(uuid.uuid4())
    await create_task(job_id, user_id=user.user_id)
    asyncio.create_task(_process_video_url(job_id, url, language=language))

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
async def upload_video(
    file: UploadFile,
    user: CurrentUser,
    language: str = "en",
):
    """Upload a local video file for processing. Returns a job_id."""
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

    language = _normalize_language(language)
    job_id = str(uuid.uuid4())

    safe_name = Path(file.filename).name if file.filename else "upload"
    safe_name = safe_name.replace("..", "")
    if not safe_name:
        safe_name = "upload"

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

    await create_task(job_id, message="Uploaded, queued", user_id=user.user_id)
    asyncio.create_task(_process_video_file(job_id, str(file_path), language=language))

    return {"job_id": job_id}


@router.get("/tasks/{job_id}/progress")
async def task_progress(
    job_id: str,
    user: CurrentUser,
):
    """SSE endpoint for real-time task progress updates."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        while True:
            task = await get_task(job_id)
            if not task:
                yield {"event": "progress", "data": json.dumps({"error": "Task not found"})}
                break
            data = {
                "stage": task["stage"],
                "progress": task["progress"],
                "message": task["message"],
            }
            yield {
                "event": "progress",
                "data": json.dumps(data),
            }
            if task["stage"] in (
                TaskStage.complete.value,
                TaskStage.failed.value,
            ):
                result_raw = task.get("result_json")
                if result_raw:
                    yield {
                        "event": "complete",
                        "data": result_raw,
                    }
                break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/tasks/{job_id}/result", response_model=NoteResponse)
async def task_result(
    job_id: str,
    user: CurrentUser,
):
    """Get the final note result for a completed task."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    result_raw = task.get("result_json")
    if not result_raw:
        if task["stage"] == TaskStage.failed.value:
            raise HTTPException(
                status_code=500,
                detail=task.get("message", "Task failed"),
            )
        raise HTTPException(status_code=202, detail="Task still processing")

    result = json.loads(result_raw)
    return NoteResponse(
        job_id=job_id,
        markdown=result.get("markdown", ""),
        title=result.get("title"),
    )


@router.get("/tasks", response_model=list[TaskListItem])
async def list_tasks(user: CurrentUser):
    """List all tasks for the current user."""
    tasks = await get_user_tasks(user.user_id)
    return [TaskListItem(**t) for t in tasks]
