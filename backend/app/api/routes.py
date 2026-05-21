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
from app.config import (
    ASR_API_BASE,
    ASR_API_KEY,
    ASR_MODEL,
    ASR_PROVIDER,
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_MODEL,
    MAX_UPLOAD_SIZE_MB,
    PROVIDER_PRESETS,
    UPLOAD_DIR,
)
from app.crypto import decrypt_api_key, encrypt_api_key
from app.db import (
    count_user_tasks,
    create_task,
    delete_task,
    get_all_provider_configs,
    get_task,
    get_user_tasks,
    save_provider_config,
    set_result,
    update_progress,
)
from app.schemas import (
    ModelItem,
    ModelsRequest,
    ModelsResponse,
    NoteResponse,
    ProviderConfigResponse,
    ProviderPreset,
    ProvidersResponse,
    SettingsRequest,
    SettingsResponse,
    TaskListItem,
    TaskListResponse,
    TaskStage,
    VideoRequest,
)
from app.services.audio import download_audio_via_ytdlp, extract_audio
from app.services.markdown import normalize_note_markdown
from app.services.note_gen import generate_notes
from app.services.subtitle import detect_video_platform, extract_subtitles, get_video_info
from app.services.transcribe import transcribe_audio

CurrentUser = Annotated[TokenData, Depends(get_current_user)]

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_LANGUAGES = {"en", "zh-CN"}


def _mask_api_key(key: str) -> str:
    """Return masked API key showing only last 4 characters."""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


async def _get_user_provider(user_id: str, category: str) -> dict | None:
    """Read user provider config from DB, decrypt api_key. Returns None if not configured."""
    configs = await get_all_provider_configs(user_id)
    config = configs.get(category)
    if not config:
        return None
    api_key = ""
    if config.get("api_key_encrypted"):
        try:
            api_key = decrypt_api_key(config["api_key_encrypted"])
        except Exception:
            api_key = ""
    return {
        "provider": config.get("provider", ""),
        "model": config.get("model", ""),
        "api_key": api_key,
        "api_base": config.get("api_base", ""),
    }


def _normalize_language(lang: str) -> str:
    """Normalize language code, fallback to 'en' if unsupported."""
    if lang in SUPPORTED_LANGUAGES:
        return lang
    if lang.startswith("zh"):
        return "zh-CN"
    return "en"


async def _process_video_url(
    job_id: str, url: str, language: str = "en", user_id: str | None = None
) -> None:
    """Process a video URL: extract subtitles or transcribe, then generate notes."""
    try:
        # Read user provider config, fallback to env defaults
        asr_cfg = await _get_user_provider(user_id, "asr") if user_id else None
        llm_cfg = await _get_user_provider(user_id, "llm") if user_id else None

        asr_api_key = asr_cfg["api_key"] if asr_cfg and asr_cfg["api_key"] else ASR_API_KEY
        asr_api_base = asr_cfg["api_base"] if asr_cfg and asr_cfg["api_base"] else ASR_API_BASE
        asr_model = asr_cfg["model"] if asr_cfg and asr_cfg["model"] else ASR_MODEL
        asr_provider = asr_cfg["provider"] if asr_cfg and asr_cfg["provider"] else ASR_PROVIDER

        llm_api_key = llm_cfg["api_key"] if llm_cfg and llm_cfg["api_key"] else LLM_API_KEY
        llm_api_base = llm_cfg["api_base"] if llm_cfg and llm_cfg["api_base"] else LLM_API_BASE
        llm_model = llm_cfg["model"] if llm_cfg and llm_cfg["model"] else LLM_MODEL

        video_info = await asyncio.to_thread(get_video_info, url)
        video_title = video_info["title"]

        await update_progress(
            job_id, TaskStage.extracting_subtitles, 0.1, "Extracting subtitles..."
        )

        subtitle_text = await asyncio.to_thread(extract_subtitles, url)

        if subtitle_text:
            transcript = subtitle_text
            await update_progress(job_id, TaskStage.extracting_subtitles, 0.5, "Subtitles found")
        else:
            await update_progress(
                job_id, TaskStage.downloading, 0.2, "No subtitles, downloading audio..."
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                audio_path = await asyncio.to_thread(download_audio_via_ytdlp, url, tmpdir)

                await update_progress(job_id, TaskStage.transcribing, 0.4, "Transcribing audio...")
                transcript = await asyncio.to_thread(
                    transcribe_audio,
                    audio_path,
                    api_key=asr_api_key,
                    api_base=asr_api_base,
                    model=asr_model,
                    provider=asr_provider,
                )

            await update_progress(job_id, TaskStage.transcribing, 0.6, "Transcription complete")

        await update_progress(job_id, TaskStage.generating_notes, 0.7, "Generating notes...")
        has_timestamps = "#t=" in transcript
        markdown = await asyncio.to_thread(
            generate_notes,
            transcript,
            video_title=video_title,
            language=language,
            api_key=llm_api_key,
            api_base=llm_api_base,
            model=llm_model,
            has_timestamps=has_timestamps,
        )

        await update_progress(job_id, TaskStage.generating_notes, 0.9, "Notes generated")

        await set_result(job_id, markdown, title=video_title)

    except Exception as e:
        logger.exception(f"Task {job_id} failed: {e}")
        await update_progress(job_id, TaskStage.failed, 0.0, f"Error: {str(e)}")


async def _process_video_file(
    job_id: str, file_path: str, language: str = "en", user_id: str | None = None
) -> None:
    """Process an uploaded video file: extract audio, transcribe, generate notes."""
    try:
        # Read user provider config, fallback to env defaults
        asr_cfg = await _get_user_provider(user_id, "asr") if user_id else None
        llm_cfg = await _get_user_provider(user_id, "llm") if user_id else None

        asr_api_key = asr_cfg["api_key"] if asr_cfg and asr_cfg["api_key"] else ASR_API_KEY
        asr_api_base = asr_cfg["api_base"] if asr_cfg and asr_cfg["api_base"] else ASR_API_BASE
        asr_model = asr_cfg["model"] if asr_cfg and asr_cfg["model"] else ASR_MODEL
        asr_provider = asr_cfg["provider"] if asr_cfg and asr_cfg["provider"] else ASR_PROVIDER

        llm_api_key = llm_cfg["api_key"] if llm_cfg and llm_cfg["api_key"] else LLM_API_KEY
        llm_api_base = llm_cfg["api_base"] if llm_cfg and llm_cfg["api_base"] else LLM_API_BASE
        llm_model = llm_cfg["model"] if llm_cfg and llm_cfg["model"] else LLM_MODEL

        await update_progress(job_id, TaskStage.transcribing, 0.1, "Extracting audio from video...")

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = str(Path(tmpdir) / "audio.wav")
            await asyncio.to_thread(extract_audio, file_path, audio_path)

            await update_progress(job_id, TaskStage.transcribing, 0.3, "Transcribing audio...")
            transcript = await asyncio.to_thread(
                transcribe_audio,
                audio_path,
                api_key=asr_api_key,
                api_base=asr_api_base,
                model=asr_model,
                provider=asr_provider,
            )

        await update_progress(job_id, TaskStage.transcribing, 0.6, "Transcription complete")

        await update_progress(job_id, TaskStage.generating_notes, 0.7, "Generating notes...")
        has_timestamps = "#t=" in transcript
        markdown = await asyncio.to_thread(
            generate_notes,
            transcript,
            language=language,
            api_key=llm_api_key,
            api_base=llm_api_base,
            model=llm_model,
            has_timestamps=has_timestamps,
        )

        await update_progress(job_id, TaskStage.generating_notes, 0.9, "Notes generated")

        await set_result(job_id, markdown)

    except Exception as e:
        logger.exception(f"Task {job_id} failed: {e}")
        await update_progress(job_id, TaskStage.failed, 0.0, f"Error: {str(e)}")
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
    video_info = await asyncio.to_thread(get_video_info, url)
    await create_task(
        job_id, user_id=user.user_id,
        video_url=url, platform=platform, language=language, source_type="url",
        thumbnail_url=video_info.get("thumbnail_url"),
    )
    asyncio.create_task(_process_video_url(job_id, url, language=language, user_id=user.user_id))

    return {"job_id": job_id}


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


@router.post("/upload")
async def upload_video(
    file: UploadFile,
    user: CurrentUser,
    language: str = "en",
):
    """Upload a local video file for processing. Returns a job_id."""
    content_type = file.content_type or ""
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if content_type not in ALLOWED_VIDEO_TYPES and ext not in ALLOWED_EXTENSIONS:
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

    await create_task(
        job_id, message="Uploaded, queued", user_id=user.user_id,
        file_name=safe_name, language=language, source_type="upload",
    )
    asyncio.create_task(
        _process_video_file(job_id, str(file_path), language=language, user_id=user.user_id)
    )

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
                TaskStage.cancelled.value,
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
        markdown=normalize_note_markdown(result.get("markdown", "")),
        title=result.get("title"),
    )


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    user: CurrentUser,
    page: int = 1,
    limit: int = 20,
    folder: str | None = None,
    tag: str | None = None,
    is_favorite: bool | None = None,
    search: str | None = None,
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
        folder_null=folder_null, search=search,
        sort_by=sort_by, sort_order=sort_order,
    )
    total = await count_user_tasks(
        user.user_id, folder_id=folder_id, tag_id=tag, is_favorite=is_favorite,
        folder_null=folder_null, search=search,
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
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    # Extract title from result_json
    title = None
    if task.get("result_json"):
        try:
            parsed = json.loads(task["result_json"])
            title = parsed.get("title")
        except (json.JSONDecodeError, TypeError):
            pass
    task["title"] = title
    return TaskListItem(**task)


@router.delete("/tasks/{job_id}")
async def cancel_or_delete_task(
    job_id: str,
    user: CurrentUser,
):
    """Delete a task. Also cancels if in progress."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    terminal_stages = (
        TaskStage.complete.value, TaskStage.failed.value, TaskStage.cancelled.value,
    )
    if task["stage"] not in terminal_stages:
        await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")

    deleted = await delete_task(job_id, user_id=user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"detail": "Task deleted"}


@router.post("/tasks/{job_id}/retry")
async def retry_task(
    job_id: str,
    user: CurrentUser,
):
    """Retry a failed URL-type task. Creates a new task with the same input."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    if task["stage"] != TaskStage.failed.value:
        raise HTTPException(status_code=409, detail="Only failed tasks can be retried")

    if task.get("source_type") != "url" or not task.get("video_url"):
        raise HTTPException(
            status_code=422,
            detail="Only URL-type tasks can be retried (uploaded files are not retained)",
        )

    video_url = task["video_url"]
    language = task.get("language") or "en"
    platform = task.get("platform") or detect_video_platform(video_url)

    new_job_id = str(uuid.uuid4())
    video_info = await asyncio.to_thread(get_video_info, video_url)
    await create_task(
        new_job_id, user_id=user.user_id,
        video_url=video_url, platform=platform, language=language, source_type="url",
        thumbnail_url=video_info.get("thumbnail_url"),
    )
    asyncio.create_task(
        _process_video_url(new_job_id, video_url, language=language, user_id=user.user_id)
    )
    return {"job_id": new_job_id}


@router.post("/tasks/{job_id}/cancel")
async def cancel_task(
    job_id: str,
    user: CurrentUser,
):
    """Cancel an in-progress task by marking it as cancelled."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    finished_stages = (
        TaskStage.complete.value, TaskStage.failed.value, TaskStage.cancelled.value,
    )
    if task["stage"] in finished_stages:
        raise HTTPException(status_code=409, detail="Task already finished")

    await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
    return {"detail": "Task cancelled"}


# --- Provider / Settings endpoints ---


@router.post("/models", response_model=ModelsResponse)
async def list_models(req: ModelsRequest, user: CurrentUser):
    """Proxy /v1/models call to avoid exposing API key to the frontend."""
    try:
        from openai import AsyncOpenAI

        async with AsyncOpenAI(api_key=req.api_key, base_url=req.api_base) as client:
            page = await client.models.list()
            models = [
                ModelItem(id=m.id, object=m.object, created=m.created, owned_by=m.owned_by)
                for m in page.data
            ]
            return ModelsResponse(models=models)
    except Exception as e:
        logger.warning(f"Failed to list models for {req.api_base}: {e}")
        return ModelsResponse(models=[], error=str(e))


@router.get("/providers", response_model=ProvidersResponse)
async def get_providers(user: CurrentUser):
    """Return preset provider/model lists for ASR and LLM."""
    return ProvidersResponse(
        asr=[ProviderPreset(**p) for p in PROVIDER_PRESETS["asr"]],
        llm=[ProviderPreset(**p) for p in PROVIDER_PRESETS["llm"]],
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(user: CurrentUser):
    """Return current user provider settings (API keys masked)."""
    configs = await get_all_provider_configs(user.user_id)
    result: dict = {}
    for category in ("asr", "llm"):
        cfg = configs.get(category)
        if cfg and cfg.get("provider"):
            api_key_masked = ""
            if cfg.get("api_key_encrypted"):
                try:
                    decrypted = decrypt_api_key(cfg["api_key_encrypted"])
                    api_key_masked = _mask_api_key(decrypted)
                except Exception:
                    api_key_masked = "****"
            result[category] = ProviderConfigResponse(
                provider=cfg["provider"],
                model=cfg["model"],
                api_key_masked=api_key_masked,
                api_base=cfg["api_base"],
            )
    return SettingsResponse(**result)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(req: SettingsRequest, user: CurrentUser):
    """Save user provider settings (API keys encrypted)."""
    existing_configs = await get_all_provider_configs(user.user_id)

    for category in ("asr", "llm"):
        cfg = getattr(req, category)
        if cfg is None:
            continue

        # If user didn't provide a new key, keep the existing one
        if cfg.api_key:
            api_key_encrypted = encrypt_api_key(cfg.api_key)
        else:
            existing = existing_configs.get(category, {})
            api_key_encrypted = existing.get("api_key_encrypted", "")

        await save_provider_config(
            user_id=user.user_id,
            category=category,
            provider=cfg.provider,
            model=cfg.model,
            api_key_encrypted=api_key_encrypted,
            api_base=cfg.api_base,
        )

    # Return updated settings (re-read to get masked keys)
    configs = await get_all_provider_configs(user.user_id)
    result: dict = {}
    for category in ("asr", "llm"):
        cfg = configs.get(category)
        if cfg and cfg.get("provider"):
            api_key_masked = ""
            if cfg.get("api_key_encrypted"):
                try:
                    decrypted = decrypt_api_key(cfg["api_key_encrypted"])
                    api_key_masked = _mask_api_key(decrypted)
                except Exception:
                    api_key_masked = "****"
            result[category] = ProviderConfigResponse(
                provider=cfg["provider"],
                model=cfg["model"],
                api_key_masked=api_key_masked,
                api_base=cfg["api_base"],
            )
    return SettingsResponse(**result)
