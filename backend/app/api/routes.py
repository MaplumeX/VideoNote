"""FastAPI routes for VideoNote — thin HTTP layer (C4).

Responsibilities are deliberately narrow: authentication, input validation,
HTTP status mapping, and upload security. All task orchestration is delegated
to ``app.pipeline.orchestrator`` / ``app.pipeline.runner``.
"""

import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app.auth import TokenData, get_current_user
from app.config import MAX_UPLOAD_SIZE_MB, UPLOAD_DIR
from app.db import (
    count_user_tasks,
    create_task,
    delete_task,
    find_active_task_by_url,
    get_task,
    get_user_tasks,
    request_task_cancel,
)
from app.errors import error_detail
from app.pipeline.context import (
    detect_video_platform,
    normalize_language,
    providers_configured,
    resolve_providers,
    wav_path_for,
)
from app.pipeline.markdown import normalize_note_markdown
from app.pipeline.orchestrator import orchestrator
from app.pipeline.runner import pipeline_runner
from app.pipeline.state import TaskStatus
from app.schemas import (
    NoteResponse,
    ProcessResponse,
    TaskListItem,
    TaskListResponse,
    UploadResponse,
    VideoRequest,
)

CurrentUser = Annotated[TokenData, Depends(get_current_user)]

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Helpers (validation / HTTP mapping only) --------------------------------

def _safe_upload_path(path_value: str | None) -> Path | None:
    """Resolve a persisted upload path and reject paths outside UPLOAD_DIR."""
    if not path_value:
        return None
    path = Path(path_value).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if path == upload_root or upload_root not in path.parents:
        return None
    return path

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\u4e00-\u9fff-]")

def _sanitize_upload_name(filename: str | None) -> str:
    """Sanitize a user-supplied filename for safe local storage.

    Takes the basename, replaces non-whitelisted characters with '_',
    strips leading dots/spaces, and collapses '..' sequences.
    """
    base = Path(filename).name if filename else "upload"
    base = _SAFE_NAME_RE.sub("_", base)
    base = base.replace("..", "_").strip(". ") or "upload"
    return base

async def _get_task_or_404(job_id: str, user_id: str) -> dict:
    task = await get_task(job_id)
    if not task or task.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND"))
    return task

def _terminal(task: dict) -> bool:
    """Terminal in either dimension (new status or legacy stage)."""
    terminal = {TaskStatus.complete, TaskStatus.failed, TaskStatus.cancelled}
    status = task.get("status")
    if status in terminal:
        return True
    legacy = task.get("stage")
    return legacy in ("complete", "failed", "cancelled")

def _iso_utc(raw: str) -> str:
    """Normalize a DB timestamp to ISO 8601 UTC for the SSE payload.

    App-written timestamps are already ISO 8601 (``datetime.now(UTC).isoformat()``);
    legacy rows written by SQLite ``CURRENT_TIMESTAMP`` use
    ``YYYY-MM-DD HH:MM:SS``. Contract §2.1 requires ISO 8601, so a space
    separator becomes ``T`` and a missing timezone gets ``+00:00``.
    """
    if not raw:
        return raw
    value = raw.replace(" ", "T", 1) if " " in raw else raw
    if "T" in value and not value.endswith(("Z", "+00:00")) and "+" not in value[10:]:
        value += "+00:00"
    return value

async def _ensure_providers_configured(user_id: str) -> None:
    provider = await resolve_providers(user_id)
    if not providers_configured(provider):
        raise HTTPException(
            status_code=422,
            detail=error_detail("PROVIDER_NOT_CONFIGURED"),
        )

# --- Task submission ----------------------------------------------------------

@router.post("/process", response_model=ProcessResponse)
async def process_video(
    request: VideoRequest,
    user: CurrentUser,
):
    """Submit a video URL for processing. Returns a job_id immediately."""
    url = str(request.url)
    platform = detect_video_platform(url)
    if platform == "unknown":
        raise HTTPException(
            status_code=422,
            detail=error_detail("UNSUPPORTED_VIDEO_PLATFORM"),
        )

    language = normalize_language(request.language)
    job_id = str(uuid.uuid4())

    # Dedupe: if an active task for the same URL already exists, return it
    existing = await find_active_task_by_url(user.user_id, url)
    if existing:
        return ProcessResponse(
            job_id=existing["job_id"],
            title=existing.get("title") or "",
            thumbnail_url=existing.get("thumbnail_url") or "",
            platform=existing.get("platform") or platform,
            source_type=existing.get("source_type") or "url",
        )

    await _ensure_providers_configured(user.user_id)

    await create_task(
        job_id, user_id=user.user_id,
        video_url=url, platform=platform, language=language, source_type="url",
        thumbnail_url=None, title=None,
    )
    await orchestrator.schedule_task(job_id)

    return ProcessResponse(
        job_id=job_id,
        title="",
        thumbnail_url="",
        platform=platform,
        source_type="url",
    )

ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/webm",
    "video/x-matroska",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-flv",
    "video/mpeg",
    "video/3gpp",
    "video/x-ms-wmv",
}

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".webm",
    ".mkv",
    ".mov",
    ".avi",
    ".flv",
    ".mpeg",
    ".3gp",
    ".wmv",
}

@router.post("/upload", response_model=UploadResponse)
async def upload_video(
    file: UploadFile,
    user: CurrentUser,
    language: Annotated[str, Form()] = "en",
):
    """Upload a local video file for processing. Returns a job_id."""
    content_type = file.content_type or ""
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if content_type not in ALLOWED_VIDEO_TYPES and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=error_detail("UNSUPPORTED_FILE_TYPE", contentType=content_type or ext),
        )

    language = normalize_language(language)
    job_id = str(uuid.uuid4())

    await _ensure_providers_configured(user.user_id)

    safe_name = _sanitize_upload_name(file.filename)
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file_path = UPLOAD_DIR / f"{job_id}_{safe_name}"

    size = 0
    upload_complete = False
    try:
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=error_detail("FILE_TOO_LARGE", maxMb=MAX_UPLOAD_SIZE_MB),
                    )
                f.write(chunk)
        upload_complete = True
    finally:
        # Client disconnect / cancellation mid-upload surfaces as an exception
        # from file.read() — remove the partial file so it doesn't leak.
        if not upload_complete:
            file_path.unlink(missing_ok=True)

    await create_task(
        job_id, message="Uploaded, queued", user_id=user.user_id,
        file_name=safe_name, language=language, source_type="upload",
        input_file_path=str(file_path.resolve()),
    )
    await orchestrator.schedule_task(job_id)

    return UploadResponse(
        job_id=job_id,
        file_name=safe_name,
        source_type="upload",
    )

# --- Task progress (SSE) / result ---------------------------------------------

@router.get("/thumbnails/{filename}")
async def get_thumbnail(filename: str):
    """Serve a locally cached thumbnail image."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail=error_detail("INVALID_FILENAME"))
    path = (UPLOAD_DIR / "thumbnails" / filename).resolve()
    if not path.is_file() or not str(path).startswith(str((UPLOAD_DIR / "thumbnails").resolve())):
        raise HTTPException(status_code=404, detail=error_detail("THUMBNAIL_NOT_FOUND"))
    return FileResponse(path)

@router.get("/tasks/{job_id}/progress")
async def task_progress(
    job_id: str,
    user: CurrentUser,
):
    """SSE endpoint for real-time task progress updates (ProgressEvent schema)."""
    await _get_task_or_404(job_id, user.user_id)

    async def event_generator():
        start_time = asyncio.get_running_loop().time()
        MAX_DURATION = 30 * 60  # 30 minutes
        HEARTBEAT_INTERVAL = 15
        last_heartbeat = start_time

        while True:
            task = await get_task(job_id)
            if not task:
                yield {"event": "progress", "data": json.dumps({"error": "Task not found"})}
                break
            data = {
                "status": task.get("status") or TaskStatus.pending.value,
                "phase": task.get("phase"),
                "phase_progress": task.get("phase_progress") or 0.0,
                "message": task.get("message") or "",
                "attempt": task.get("attempt_count") or 0,
                "timestamp": _iso_utc(task.get("updated_at") or ""),
            }
            yield {
                "event": "progress",
                "data": json.dumps(data),
            }
            if _terminal(task):
                result_raw = task.get("result_json")
                if result_raw:
                    yield {
                        "event": "complete",
                        "data": result_raw,
                    }
                break

            now = asyncio.get_running_loop().time()
            if now - start_time > MAX_DURATION:
                return  # Close connection; frontend reconnects automatically
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                yield {"event": "ping", "data": ""}
                last_heartbeat = now
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())

@router.get("/tasks/{job_id}/result", response_model=NoteResponse)
async def task_result(
    job_id: str,
    user: CurrentUser,
):
    """Get the final note result for a completed task."""
    task = await _get_task_or_404(job_id, user.user_id)

    result_raw = task.get("result_json")
    if not result_raw:
        if task.get("status") == TaskStatus.failed.value or task.get("stage") == "failed":
            raise HTTPException(
                status_code=500,
                detail=error_detail("TASK_FAILED", message=task.get("message", "")),
            )
        raise HTTPException(status_code=202, detail=error_detail("TASK_STILL_PROCESSING"))

    result = json.loads(result_raw)
    return NoteResponse(
        job_id=job_id,
        markdown=normalize_note_markdown(result.get("markdown", "")),
        title=result.get("title"),
    )

# --- Task list / detail / delete -----------------------------------------------

@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    user: CurrentUser,
    page: int = 1,
    limit: int = 20,
    folder: str | None = None,
    tag: str | None = None,
    is_favorite: bool | None = None,
    search: str | None = None,
    exclude_cancelled: bool = False,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    """List tasks for the current user with pagination and optional filters."""
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20
    offset = (page - 1) * limit
    # "none" is a special value meaning "filter for uncategorized notes (folder_id IS NULL)"
    folder_id = None if folder == "none" else folder
    folder_null = folder == "none"
    tasks = await get_user_tasks(
        user.user_id, limit=limit, offset=offset,
        folder_id=folder_id, tag_id=tag, is_favorite=is_favorite,
        folder_null=folder_null, search=search, exclude_cancelled=exclude_cancelled,
        sort_by=sort_by, sort_order=sort_order,
    )
    total = await count_user_tasks(
        user.user_id, folder_id=folder_id, tag_id=tag, is_favorite=is_favorite,
        folder_null=folder_null, search=search, exclude_cancelled=exclude_cancelled,
    )
    return TaskListResponse(
        items=[TaskListItem(**t) for t in tasks],
        total=total,
        page=page,
        limit=limit,
    )

@router.get("/tasks/{job_id}", response_model=TaskListItem)
async def get_single_task(
    job_id: str,
    user: CurrentUser,
):
    """Get a single task by job_id."""
    task = await _get_task_or_404(job_id, user.user_id)
    # Extract title: prefer DB column, fall back to result_json
    title = task.get("title") or None
    if not title and task.get("result_json"):
        try:
            parsed = json.loads(task["result_json"])
            title = parsed.get("title")
        except (json.JSONDecodeError, TypeError):
            pass
    task["title"] = title
    # New-chain rows created before their first status write have NULL
    # status; display via the same backfilled mapping the list uses.
    if task.get("status") is None:
        legacy = task.get("stage")
        task["status"] = (
            legacy if legacy in ("complete", "failed", "cancelled") else "pending"
        )
    return TaskListItem(**task)

@router.delete("/tasks/{job_id}")
async def cancel_or_delete_task(
    job_id: str,
    user: CurrentUser,
):
    """Delete a task. Also cancels if in progress."""
    task = await _get_task_or_404(job_id, user.user_id)

    if not _terminal(task):
        await request_task_cancel(job_id, user_id=user.user_id)
        orchestrator.cancel(job_id)
        await pipeline_runner.cancel_and_wait(job_id)

    if input_path := _safe_upload_path(task.get("input_file_path")):
        input_path.unlink(missing_ok=True)
    # Delete is terminal: the retained per-job WAV (kept on failure for
    # checkpoint-resumed retries) must go away with the task row.
    wav_path_for(job_id).unlink(missing_ok=True)
    deleted = await delete_task(job_id, user_id=user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND"))
    return {"detail": "Task deleted"}

# --- Retry / cancel -------------------------------------------------------------

@router.post("/tasks/{job_id}/retry", response_model=ProcessResponse)
async def retry_task(
    job_id: str,
    user: CurrentUser,
):
    """Retry a failed/cancelled task, resuming from its persisted checkpoint."""
    task = await _get_task_or_404(job_id, user.user_id)

    retryable = {TaskStatus.failed, TaskStatus.cancelled}
    status = task.get("status")
    legacy = task.get("stage")
    if status not in retryable and legacy not in ("failed", "cancelled"):
        raise HTTPException(status_code=409, detail=error_detail("ONLY_FAILED_CAN_RETRY"))

    await _ensure_providers_configured(user.user_id)

    if not await orchestrator.retry(job_id):
        raise HTTPException(status_code=409, detail=error_detail("ONLY_FAILED_CAN_RETRY"))

    source_type = task.get("source_type") or "url"
    return ProcessResponse(
        job_id=job_id,
        title="",
        thumbnail_url="",
        platform=task.get("platform") or "",
        source_type=source_type,
    )

@router.post("/tasks/{job_id}/cancel")
async def cancel_task(
    job_id: str,
    user: CurrentUser,
):
    """Cancel an in-progress task by marking it as cancelled."""
    task = await _get_task_or_404(job_id, user.user_id)

    if _terminal(task):
        raise HTTPException(status_code=409, detail=error_detail("TASK_ALREADY_FINISHED"))

    cancelled = await request_task_cancel(job_id, user_id=user.user_id)
    if not cancelled:
        raise HTTPException(status_code=409, detail=error_detail("TASK_ALREADY_FINISHED"))
    orchestrator.cancel(job_id)
    pipeline_runner.cancel(job_id)
    return {"detail": "Task cancelled"}
