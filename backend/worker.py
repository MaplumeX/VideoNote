"""ARQ worker for VideoNote video processing tasks."""

import json
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import redis.asyncio as aioredis
from arq.connections import RedisSettings

from app.config import REDIS_URL
from app.schemas import TaskStage
from app.services.audio import download_audio_via_ytdlp, extract_audio
from app.services.note_gen import generate_notes
from app.services.subtitle import extract_subtitles, get_video_title
from app.services.transcribe import transcribe_audio

logger = logging.getLogger(__name__)


def _parse_redis_url(url: str) -> RedisSettings:
    """Parse redis://host:port/db into ARQ RedisSettings."""
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


redis_settings = _parse_redis_url(REDIS_URL)


async def set_progress(
    job_id: str, stage: TaskStage, progress: float, message: str = ""
):
    """Update task progress in Redis."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        data = {
            "stage": stage.value,
            "progress": progress,
            "message": message,
        }
        await r.hset(
            f"videonote:task:{job_id}", "progress", json.dumps(data)
        )
    finally:
        await r.aclose()


async def set_result(job_id: str, markdown: str, title: str | None = None):
    """Store final note result in Redis."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.hset(
            f"videonote:task:{job_id}",
            mapping={
                "result": json.dumps({"markdown": markdown, "title": title}),
                "progress": json.dumps({
                    "stage": TaskStage.complete.value,
                    "progress": 1.0,
                    "message": "Done",
                }),
            },
        )
        # Expire after 1 hour
        await r.expire(f"videonote:task:{job_id}", 3600)
    finally:
        await r.aclose()


async def process_video_url(ctx: dict, job_id: str, url: str):
    """Process a video URL: extract subtitles or transcribe, then generate notes."""
    try:
        # Get video title for note generation
        video_title = get_video_title(url)

        # Stage 1: Try subtitle extraction
        await set_progress(
            job_id, TaskStage.extracting_subtitles, 0.1,
            "Extracting subtitles..."
        )

        subtitle_text = extract_subtitles(url)

        if subtitle_text:
            transcript = subtitle_text
            await set_progress(
                job_id, TaskStage.extracting_subtitles, 0.5,
                "Subtitles found"
            )
        else:
            # Fallback: download audio and transcribe
            await set_progress(
                job_id, TaskStage.downloading, 0.2,
                "No subtitles, downloading audio..."
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                audio_path = download_audio_via_ytdlp(url, tmpdir)

                await set_progress(
                    job_id, TaskStage.transcribing, 0.4,
                    "Transcribing audio..."
                )
                transcript = transcribe_audio(audio_path)

            await set_progress(
                job_id, TaskStage.transcribing, 0.6,
                "Transcription complete"
            )

        # Stage 2: Generate notes
        await set_progress(
            job_id, TaskStage.generating_notes, 0.7, "Generating notes..."
        )
        markdown = generate_notes(transcript, video_title=video_title)

        await set_progress(
            job_id, TaskStage.generating_notes, 0.9, "Notes generated"
        )

        # Store result
        await set_result(job_id, markdown, title=video_title)

    except Exception as e:
        logger.exception(f"Task {job_id} failed: {e}")
        await set_progress(
            job_id, TaskStage.failed, 0.0, f"Error: {str(e)}"
        )


async def process_video_file(ctx: dict, job_id: str, file_path: str):
    """Process an uploaded video file: extract audio, transcribe, generate notes."""
    try:
        await set_progress(
            job_id, TaskStage.transcribing, 0.1,
            "Extracting audio from video..."
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = str(Path(tmpdir) / "audio.wav")
            extract_audio(file_path, audio_path)

            await set_progress(
                job_id, TaskStage.transcribing, 0.3,
                "Transcribing audio..."
            )
            transcript = transcribe_audio(audio_path)

        await set_progress(
            job_id, TaskStage.transcribing, 0.6, "Transcription complete"
        )

        # Generate notes
        await set_progress(
            job_id, TaskStage.generating_notes, 0.7, "Generating notes..."
        )
        markdown = generate_notes(transcript)

        await set_progress(
            job_id, TaskStage.generating_notes, 0.9, "Notes generated"
        )

        # Store result
        await set_result(job_id, markdown)

        # Clean up uploaded file
        Path(file_path).unlink(missing_ok=True)

    except Exception as e:
        logger.exception(f"Task {job_id} failed: {e}")
        await set_progress(
            job_id, TaskStage.failed, 0.0, f"Error: {str(e)}"
        )


class WorkerSettings:
    """ARQ worker settings."""
    functions = [process_video_url, process_video_file]
    redis_settings = redis_settings
