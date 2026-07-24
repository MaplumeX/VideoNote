"""FastAPI routes for VideoNote."""

import asyncio
import json
import logging
import re
import shutil
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
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
    MAX_TASK_ATTEMPTS,
    clear_task_input_file,
    count_user_tasks,
    create_task,
    delete_task,
    find_active_task_by_url,
    get_all_provider_configs,
    get_recoverable_tasks,
    get_task,
    get_user_cookie,
    get_user_tasks,
    is_task_cancelled,
    request_task_cancel,
    save_provider_config,
    set_result,
    update_progress,
    update_task_meta,
)
from app.errors import error_detail
from app.schemas import (
    ModelItem,
    ModelsRequest,
    ModelsResponse,
    NoteResponse,
    ProcessResponse,
    ProviderConfigResponse,
    ProviderPreset,
    ProvidersResponse,
    SettingsRequest,
    SettingsResponse,
    TaskListItem,
    TaskListResponse,
    TaskStage,
    UploadResponse,
    VideoRequest,
)
from app.services.audio import download_audio_via_ytdlp, extract_audio
from app.services.markdown import normalize_note_markdown
from app.services.note_gen import generate_notes
from app.services.subtitle import (
    detect_video_platform,
    download_thumbnail,
    extract_subtitles,
    get_video_info_strict,
)
from app.services.transcribe import transcribe_audio
from app.task_runner import task_runner

CurrentUser = Annotated[TokenData, Depends(get_current_user)]

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_LANGUAGES = {"en", "zh-CN", "ja"}


async def _cancellation_checkpoint(job_id: str) -> None:
    """Stop processing if cancellation was persisted or the task was deleted."""
    if await is_task_cancelled(job_id):
        raise asyncio.CancelledError


async def _to_thread_with_cancel(
    func: Callable[..., object],
    *args: object,
    cancel_event: threading.Event | None = None,
    timeout: float = 3.0,
    **kwargs: object,
) -> object:
    """Run a blocking call in a thread, polling cancel_event every ``timeout`` seconds.

    Unlike ``asyncio.to_thread`` alone, this exposes cancellation within the
    ``extract_info`` phase (where yt-dlp progress_hooks don't fire). When the
    event is set, the asyncio task is cancelled so the route layer can record
    ``TaskStage.cancelled`` promptly. The underlying thread continues until
    yt-dlp returns and is then garbage-collected.
    """
    while True:
        fut = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
        done, _ = await asyncio.wait({fut}, timeout=timeout)
        if fut in done:
            return fut.result()
        if cancel_event is not None and cancel_event.is_set():
            fut.cancel()
            raise asyncio.CancelledError


def _safe_upload_path(path_value: str | None) -> Path | None:
    """Resolve a persisted upload path and reject paths outside UPLOAD_DIR."""
    if not path_value:
        return None
    path = Path(path_value).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if path == upload_root or upload_root not in path.parents:
        return None
    return path


# --- Error detail sanitization ---

_API_KEY_RE = re.compile(r"sk-[A-Za-z0-9-_]{8,}")
_BEARER_RE = re.compile(r"[Bb]earer\s+[A-Za-z0-9\-_.=]+")
_COOKIE_RE = re.compile(r"(?:set-)?cookie:\s*[^\n;]+", re.IGNORECASE)


def _sanitize_error_detail(exc: Exception) -> str:
    """Strip sensitive data (API keys, Bearer tokens, cookies) from exception text.

    Returns a sanitized string truncated to 200 characters, or empty string.
    """
    raw = str(exc)
    raw = _API_KEY_RE.sub("[REDACTED]", raw)
    raw = _BEARER_RE.sub("[REDACTED]", raw)
    raw = _COOKIE_RE.sub("[REDACTED]", raw)
    raw = raw.strip()
    if len(raw) > 200:
        raw = raw[:200]
    return raw


# --- Upload filename sanitization ---

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


def _subtitle_languages(note_lang: str) -> list[str]:
    """Reorder subtitle language preference based on user's note language."""
    if note_lang.startswith("zh"):
        return ["zh-Hans", "zh", "en", "ja"]
    return ["en", "zh-Hans", "zh", "ja"]


_ASR_LANG_MAP = {"zh-CN": "zh", "en": "en", "ja": "ja"}


def _asr_language(note_lang: str) -> str | None:
    """Map note-language code to a Whisper language code.

    Returns None for unmapped languages so Whisper auto-detects.
    """
    return _ASR_LANG_MAP.get(note_lang)


async def _get_user_cookiefile(user_id: str, url: str) -> str | None:
    """Get a temp cookie file path for the user's per-user cookie matching the URL's platform.

    Returns None if no per-user cookie exists for the detected platform.
    The caller must clean up the temp file after use.
    """
    platform = detect_video_platform(url)
    if platform not in ("youtube", "bilibili"):
        return None
    record = await get_user_cookie(user_id, platform)
    if not record or not record.get("cookie_encrypted"):
        return None
    try:
        cookie_content = decrypt_api_key(record["cookie_encrypted"])
    except Exception:
        logger.warning(f"Failed to decrypt cookie for user {user_id} platform {platform}")
        return None
    if not cookie_content:
        return None
    # Write decrypted cookie to a temp file
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, prefix="cookie_")
    tmp.write(cookie_content)
    tmp.close()
    return tmp.name


# --- Shared helpers for _process_video_url / _process_video_file ---


@dataclass
class ProviderBundle:
    """Resolved ASR + LLM provider configuration (user config with env fallback)."""

    asr_api_key: str
    asr_api_base: str
    asr_model: str
    asr_provider: str
    llm_api_key: str
    llm_api_base: str
    llm_model: str


@dataclass
class _StageFailed(Exception):
    """Raised by stage helpers to signal failure or cancellation.

    code: stable error code (e.g. "TRANSCRIPTION_FAILED").
    detail: sanitized exception summary (empty for now; wired in Phase C).
    cancelled: True when the stage was interrupted by a cancel request.
    """

    code: str = ""
    detail: str = ""
    cancelled: bool = False


async def _resolve_providers(user_id: str | None) -> ProviderBundle:
    """Read user provider config from DB, falling back to env defaults."""
    asr_cfg = await _get_user_provider(user_id, "asr") if user_id else None
    llm_cfg = await _get_user_provider(user_id, "llm") if user_id else None

    return ProviderBundle(
        asr_api_key=asr_cfg["api_key"] if asr_cfg and asr_cfg["api_key"] else ASR_API_KEY,
        asr_api_base=asr_cfg["api_base"] if asr_cfg and asr_cfg["api_base"] else ASR_API_BASE,
        asr_model=asr_cfg["model"] if asr_cfg and asr_cfg["model"] else ASR_MODEL,
        asr_provider=asr_cfg["provider"] if asr_cfg and asr_cfg["provider"] else ASR_PROVIDER,
        llm_api_key=llm_cfg["api_key"] if llm_cfg and llm_cfg["api_key"] else LLM_API_KEY,
        llm_api_base=llm_cfg["api_base"] if llm_cfg and llm_cfg["api_base"] else LLM_API_BASE,
        llm_model=llm_cfg["model"] if llm_cfg and llm_cfg["model"] else LLM_MODEL,
    )


async def _ensure_providers_configured(user_id: str | None) -> str | None:
    """Return 'PROVIDER_NOT_CONFIGURED' if ASR or LLM provider is incomplete, else None."""
    providers = await _resolve_providers(user_id)
    if not providers.asr_api_key or not providers.llm_api_key:
        return "PROVIDER_NOT_CONFIGURED"
    if not providers.asr_api_base or not providers.asr_model:
        return "PROVIDER_NOT_CONFIGURED"
    if not providers.llm_api_base or not providers.llm_model:
        return "PROVIDER_NOT_CONFIGURED"
    return None


def _make_asr_progress_cb(
    job_id: str,
    loop: asyncio.AbstractEventLoop,
    cancel_event: threading.Event | None,
    base: float,
    span: float,
) -> Callable[[float, str], None]:
    """Create a progress callback that maps ASR fraction to the [base, base+span] range."""

    def _cb(fraction: float, msg: str) -> None:
        if cancel_event is not None and cancel_event.is_set():
            return
        progress = base + fraction * span
        asyncio.run_coroutine_threadsafe(
            update_progress(job_id, TaskStage.transcribing, progress, msg),
            loop,
        )

    return _cb


def _make_note_progress_cb(
    job_id: str,
    loop: asyncio.AbstractEventLoop,
) -> Callable[[float, str], None]:
    """Create a progress callback for note generation (passes fraction directly)."""

    def _cb(fraction: float, msg: str) -> None:
        asyncio.run_coroutine_threadsafe(
            update_progress(job_id, TaskStage.generating_notes, fraction, msg), loop
        )

    return _cb


async def _run_asr(
    job_id: str,
    audio_path: str,
    language: str,
    providers: ProviderBundle,
    cancel_event: threading.Event | None,
    progress_cb: Callable[[float, str], None],
) -> str:
    """Run ASR transcription. Raises _StageFailed on failure or cancellation."""
    try:
        transcript = await asyncio.to_thread(
            transcribe_audio,
            audio_path,
            language=_asr_language(language),
            api_key=providers.asr_api_key,
            api_base=providers.asr_api_base,
            model=providers.asr_model,
            provider=providers.asr_provider,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            raise _StageFailed(cancelled=True) from e
        raise _StageFailed(code="TRANSCRIPTION_FAILED", detail=_sanitize_error_detail(e)) from e
    return transcript


async def _run_note_gen(
    job_id: str,
    transcript: str,
    video_title: str | None,
    language: str,
    providers: ProviderBundle,
    cancel_event: threading.Event | None,
    progress_cb: Callable[[float, str], None],
    has_timestamps: bool,
) -> str:
    """Run note generation. Raises _StageFailed on failure or cancellation."""
    try:
        markdown = await asyncio.to_thread(
            generate_notes,
            transcript,
            video_title=video_title,
            language=language,
            api_key=providers.llm_api_key,
            api_base=providers.llm_api_base,
            model=providers.llm_model,
            has_timestamps=has_timestamps,
            cancel_event=cancel_event,
            progress_cb=progress_cb,
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            raise _StageFailed(cancelled=True) from e
        raise _StageFailed(code="NOTE_GENERATION_FAILED", detail=_sanitize_error_detail(e)) from e
    return markdown


async def _process_video_url(
    job_id: str, url: str, language: str = "en", user_id: str | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Process a video URL: extract subtitles or transcribe, then generate notes."""
    # Resolve per-user cookie file
    cookiefile_path: str | None = None
    if user_id:
        cookiefile_path = await _get_user_cookiefile(user_id, url)

    try:
        await _cancellation_checkpoint(job_id)
        providers = await _resolve_providers(user_id)

        await update_progress(
            job_id, TaskStage.downloading, 0.02, "FETCHING_VIDEO_INFO"
        )

        # Video info (fatal) + thumbnail (non-fatal)
        try:
            video_info = await _to_thread_with_cancel(
                get_video_info_strict, url, cookiefile_path=cookiefile_path,
                cancel_event=cancel_event,
            )
            await _cancellation_checkpoint(job_id)
            video_title = video_info["title"]
            ext_thumb = video_info.get("thumbnail_url") or ""
            video_info_dict = video_info.get("info")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if cancel_event is not None and cancel_event.is_set():
                await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
                return
            logger.exception(f"Task {job_id} video fetch failed: {e}")
            code = getattr(e, "code", None) or "VIDEO_FETCH_FAILED"
            detail = _sanitize_error_detail(e)
            message = f"{code}: {detail}" if detail else code
            await update_progress(job_id, TaskStage.failed, 0.0, message)
            return

        # Thumbnail download is non-fatal.
        thumbnail_filename = None
        if ext_thumb:
            try:
                thumbnail_filename = await asyncio.to_thread(download_thumbnail, ext_thumb)
            except Exception:
                logger.warning(f"Thumbnail download failed for {job_id}", exc_info=True)
        await update_task_meta(job_id, video_title, thumbnail_filename)

        await update_progress(
            job_id, TaskStage.extracting_subtitles, 0.10, "Extracting subtitles..."
        )

        subtitle_text = await _to_thread_with_cancel(
            extract_subtitles, url,
            languages=_subtitle_languages(language),
            cookiefile_path=cookiefile_path,
            cancel_event=cancel_event,
            info=video_info_dict,
        )
        await _cancellation_checkpoint(job_id)

        if subtitle_text:
            transcript = subtitle_text
            await update_progress(job_id, TaskStage.extracting_subtitles, 0.30, "Subtitles found")
        else:
            await update_progress(
                job_id, TaskStage.downloading, 0.15, "No subtitles, downloading audio..."
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    audio_path = await _to_thread_with_cancel(
                        download_audio_via_ytdlp, url, tmpdir,
                        cookiefile_path=cookiefile_path,
                        cancel_event=cancel_event,
                        info=video_info_dict,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if cancel_event is not None and cancel_event.is_set():
                        await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
                        return
                    logger.exception(f"Task {job_id} audio download failed: {e}")
                    detail = _sanitize_error_detail(e)
                    message = f"VIDEO_FETCH_FAILED: {detail}" if detail else "VIDEO_FETCH_FAILED"
                    await update_progress(
                        job_id, TaskStage.failed, 0.0, message
                    )
                    return
                await _cancellation_checkpoint(job_id)

                await update_progress(job_id, TaskStage.transcribing, 0.30, "Transcribing audio...")
                loop = asyncio.get_running_loop()
                asr_cb = _make_asr_progress_cb(job_id, loop, cancel_event, base=0.30, span=0.30)
                try:
                    transcript = await _run_asr(
                        job_id, audio_path, language, providers, cancel_event, asr_cb,
                    )
                except _StageFailed as sf:
                    if sf.cancelled:
                        await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
                    else:
                        logger.exception(f"Task {job_id} transcription failed")
                        message = f"{sf.code}: {sf.detail}" if sf.detail else sf.code
                        await update_progress(job_id, TaskStage.failed, 0.0, message)
                    return
                await _cancellation_checkpoint(job_id)

            await update_progress(job_id, TaskStage.transcribing, 0.60, "Transcription complete")

        await update_progress(job_id, TaskStage.generating_notes, 0.65, "Generating notes...")
        has_timestamps = "#t=" in transcript
        loop = asyncio.get_running_loop()
        note_cb = _make_note_progress_cb(job_id, loop)
        try:
            markdown = await _run_note_gen(
                job_id, transcript, video_title, language,
                providers, cancel_event, note_cb, has_timestamps,
            )
        except _StageFailed as sf:
            if sf.cancelled:
                await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
            else:
                logger.exception(f"Task {job_id} note generation failed")
                message = f"{sf.code}: {sf.detail}" if sf.detail else sf.code
                await update_progress(job_id, TaskStage.failed, 0.0, message)
            return
        await _cancellation_checkpoint(job_id)

        await set_result(job_id, markdown, title=video_title)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
        else:
            logger.exception(f"Task {job_id} failed: {e}")
            detail = _sanitize_error_detail(e)
            message = f"PROCESSING_FAILED: {detail}" if detail else "PROCESSING_FAILED"
            await update_progress(job_id, TaskStage.failed, 0.0, message)
    finally:
        # Clean up temp cookie file
        if cookiefile_path:
            Path(cookiefile_path).unlink(missing_ok=True)


async def _process_video_file(
    job_id: str, file_path: str, language: str = "en", user_id: str | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Process an uploaded video file: extract audio, transcribe, generate notes."""
    try:
        await _cancellation_checkpoint(job_id)
        providers = await _resolve_providers(user_id)

        await update_progress(job_id, TaskStage.downloading, 0.05, "Extracting audio from video...")

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = str(Path(tmpdir) / "audio.wav")
            try:
                await asyncio.to_thread(
                    extract_audio, file_path, audio_path, cancel_event=cancel_event
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if cancel_event is not None and cancel_event.is_set():
                    await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
                    return
                logger.exception(f"Task {job_id} audio extraction failed: {e}")
                detail = _sanitize_error_detail(e)
                message = (
                    f"AUDIO_EXTRACTION_FAILED: {detail}"
                    if detail else "AUDIO_EXTRACTION_FAILED"
                )
                await update_progress(
                    job_id, TaskStage.failed, 0.0, message
                )
                return
            await _cancellation_checkpoint(job_id)

            await update_progress(job_id, TaskStage.transcribing, 0.20, "Transcribing audio...")
            loop = asyncio.get_running_loop()
            asr_cb = _make_asr_progress_cb(job_id, loop, cancel_event, base=0.20, span=0.40)
            try:
                transcript = await _run_asr(
                    job_id, audio_path, language, providers, cancel_event, asr_cb,
                )
            except _StageFailed as sf:
                if sf.cancelled:
                    await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
                else:
                    logger.exception(f"Task {job_id} transcription failed")
                    message = f"{sf.code}: {sf.detail}" if sf.detail else sf.code
                    await update_progress(job_id, TaskStage.failed, 0.0, message)
                return
            await _cancellation_checkpoint(job_id)

        await update_progress(job_id, TaskStage.transcribing, 0.60, "Transcription complete")

        await update_progress(job_id, TaskStage.generating_notes, 0.65, "Generating notes...")
        has_timestamps = "#t=" in transcript
        loop = asyncio.get_running_loop()
        note_cb = _make_note_progress_cb(job_id, loop)
        try:
            markdown = await _run_note_gen(
                job_id, transcript, None, language,
                providers, cancel_event, note_cb, has_timestamps,
            )
        except _StageFailed as sf:
            if sf.cancelled:
                await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
            else:
                logger.exception(f"Task {job_id} note generation failed")
                message = f"{sf.code}: {sf.detail}" if sf.detail else sf.code
                await update_progress(job_id, TaskStage.failed, 0.0, message)
            return
        await _cancellation_checkpoint(job_id)

        await set_result(job_id, markdown)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
        else:
            logger.exception(f"Task {job_id} failed: {e}")
            detail = _sanitize_error_detail(e)
            message = f"PROCESSING_FAILED: {detail}" if detail else "PROCESSING_FAILED"
            await update_progress(job_id, TaskStage.failed, 0.0, message)
    finally:
        task = await get_task(job_id)
        if task is None or task["stage"] in (
            TaskStage.complete.value,
            TaskStage.cancelled.value,
        ):
            Path(file_path).unlink(missing_ok=True)
            if task is not None:
                await clear_task_input_file(job_id)


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

    language = _normalize_language(request.language)
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

    not_configured = await _ensure_providers_configured(user.user_id)
    if not_configured:
        raise HTTPException(
            status_code=422, detail=error_detail(not_configured),
        )

    await create_task(
        job_id, user_id=user.user_id,
        video_url=url, platform=platform, language=language, source_type="url",
        thumbnail_url=None, title=None,
    )
    task_runner.schedule(
        job_id,
        lambda ev: _process_video_url(
            job_id, url, language=language, user_id=user.user_id, cancel_event=ev
        ),
    )

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

    language = _normalize_language(language)
    job_id = str(uuid.uuid4())

    not_configured = await _ensure_providers_configured(user.user_id)
    if not_configured:
        raise HTTPException(
            status_code=422, detail=error_detail(not_configured),
        )

    safe_name = _sanitize_upload_name(file.filename)
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
                    detail=error_detail("FILE_TOO_LARGE", maxMb=MAX_UPLOAD_SIZE_MB),
                )
            f.write(chunk)

    await create_task(
        job_id, message="Uploaded, queued", user_id=user.user_id,
        file_name=safe_name, language=language, source_type="upload",
        input_file_path=str(file_path.resolve()),
    )
    task_runner.schedule(
        job_id,
        lambda ev: _process_video_file(
            job_id, str(file_path), language=language, user_id=user.user_id, cancel_event=ev
        ),
    )

    return UploadResponse(
        job_id=job_id,
        file_name=safe_name,
        source_type="upload",
    )


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
    """SSE endpoint for real-time task progress updates."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND"))

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
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND"))

    result_raw = task.get("result_json")
    if not result_raw:
        if task["stage"] == TaskStage.failed.value:
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
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND"))
    # Extract title: prefer DB column, fall back to result_json
    title = task.get("title") or None
    if not title and task.get("result_json"):
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
        raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND"))

    terminal_stages = (
        TaskStage.complete.value, TaskStage.failed.value, TaskStage.cancelled.value,
    )
    if task["stage"] not in terminal_stages:
        await request_task_cancel(job_id, user_id=user.user_id)
        await task_runner.cancel_and_wait(job_id)

    if input_path := _safe_upload_path(task.get("input_file_path")):
        input_path.unlink(missing_ok=True)
    deleted = await delete_task(job_id, user_id=user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND"))
    return {"detail": "Task deleted"}


@router.post("/tasks/{job_id}/retry", response_model=ProcessResponse)
async def retry_task(
    job_id: str,
    user: CurrentUser,
):
    """Retry a failed task. Creates a new task with the same input."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND"))

    if task["stage"] != TaskStage.failed.value:
        raise HTTPException(status_code=409, detail=error_detail("ONLY_FAILED_CAN_RETRY"))

    not_configured = await _ensure_providers_configured(user.user_id)
    if not_configured:
        raise HTTPException(
            status_code=422, detail=error_detail(not_configured),
        )

    language = task.get("language") or "en"
    new_job_id = str(uuid.uuid4())
    source_type = task.get("source_type")

    if source_type == "url" and task.get("video_url"):
        video_url = task["video_url"]
        platform = task.get("platform") or detect_video_platform(video_url)
        await create_task(
            new_job_id, user_id=user.user_id,
            video_url=video_url, platform=platform, language=language, source_type="url",
            thumbnail_url=None, title=None,
        )
        task_runner.schedule(
            new_job_id,
            lambda ev: _process_video_url(
                new_job_id, video_url, language=language, user_id=user.user_id, cancel_event=ev
            ),
        )
        return ProcessResponse(
            job_id=new_job_id,
            title="",
            thumbnail_url="",
            platform=platform,
            source_type="url",
        )

    if source_type == "upload":
        file_path = _safe_upload_path(task.get("input_file_path"))
        if not file_path or not file_path.is_file():
            raise HTTPException(status_code=422, detail=error_detail("UPLOAD_FILE_MISSING"))
        file_name = task.get("file_name") or "upload"
        safe_name = _sanitize_upload_name(file_name)
        new_file_path = UPLOAD_DIR / f"{new_job_id}_{safe_name}"
        shutil.copy2(file_path, new_file_path)
        await create_task(
            new_job_id, message="Uploaded, queued", user_id=user.user_id,
            file_name=file_name, language=language, source_type="upload",
            input_file_path=str(new_file_path.resolve()),
        )
        task_runner.schedule(
            new_job_id,
            lambda ev: _process_video_file(
                new_job_id, str(new_file_path),
                language=language, user_id=user.user_id, cancel_event=ev,
            ),
        )
        return ProcessResponse(
            job_id=new_job_id,
            title="",
            thumbnail_url="",
            platform="",
            source_type="upload",
        )

    raise HTTPException(status_code=422, detail=error_detail("TASK_NOT_RETRYABLE"))


@router.post("/tasks/{job_id}/cancel")
async def cancel_task(
    job_id: str,
    user: CurrentUser,
):
    """Cancel an in-progress task by marking it as cancelled."""
    task = await get_task(job_id)
    if not task or task.get("user_id") != user.user_id:
        raise HTTPException(status_code=404, detail=error_detail("TASK_NOT_FOUND"))

    finished_stages = (
        TaskStage.complete.value, TaskStage.failed.value, TaskStage.cancelled.value,
    )
    if task["stage"] in finished_stages:
        raise HTTPException(status_code=409, detail=error_detail("TASK_ALREADY_FINISHED"))

    cancelled = await request_task_cancel(job_id, user_id=user.user_id)
    if not cancelled:
        raise HTTPException(status_code=409, detail=error_detail("TASK_ALREADY_FINISHED"))
    task_runner.cancel(job_id)
    return {"detail": "Task cancelled"}


async def recover_incomplete_tasks() -> None:
    """Reschedule durable non-terminal tasks after application startup."""
    for task in await get_recoverable_tasks():
        job_id = task["job_id"]

        if task.get("attempt_count", 0) >= MAX_TASK_ATTEMPTS:
            await update_progress(
                job_id, TaskStage.failed, 0.0, "TASK_RECOVERY_MAX_ATTEMPTS"
            )
            continue

        language = _normalize_language(task.get("language") or "en")
        user_id = task.get("user_id")
        source_type = task.get("source_type")

        if source_type == "url" and task.get("video_url"):
            url = task["video_url"]
            if detect_video_platform(url) == "unknown":
                await update_progress(
                    job_id,
                    TaskStage.failed,
                    0.0,
                    "TASK_RECOVERY_UNSUPPORTED_URL",
                )
                continue
            task_runner.schedule(
                job_id,
                lambda ev, job_id=job_id, url=url, language=language, user_id=user_id: (
                    _process_video_url(
                        job_id, url, language=language, user_id=user_id, cancel_event=ev
                    )
                ),
            )
            continue

        if source_type == "upload":
            file_path = _safe_upload_path(task.get("input_file_path"))
            if file_path is not None and file_path.is_file():
                task_runner.schedule(
                    job_id,
                    lambda ev, job_id=job_id,
                    file_path=file_path,
                    language=language,
                    user_id=user_id: _process_video_file(
                        job_id, str(file_path), language=language, user_id=user_id,
                        cancel_event=ev
                    ),
                )
                continue

        await update_progress(
            job_id,
            TaskStage.failed,
            0.0,
            "TASK_RECOVERY_INPUT_INVALID",
        )


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
        return ModelsResponse(models=[], error="MODELS_FETCH_FAILED")


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
