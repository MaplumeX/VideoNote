"""Transcription via OpenAI Whisper API or SiliconFlow API."""

import logging
import os
import subprocess
import tempfile

from openai import OpenAI

from app.config import ASR_API_BASE, ASR_API_KEY, ASR_MODEL, ASR_PROVIDER

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES_OPENAI = 25 * 1024 * 1024
MAX_FILE_SIZE_BYTES_SILICONFLOW = 50 * 1024 * 1024


def transcribe_audio(
    audio_path: str,
    language: str = "zh",
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> str:
    """Transcribe an audio file using configured ASR provider.

    Handles the file size limit by splitting large files when needed.
    Returns the full transcript text.

    Optional runtime parameters override the module-level config defaults.
    """
    _api_key = api_key or ASR_API_KEY
    _api_base = api_base or ASR_API_BASE
    _model = model or ASR_MODEL
    _provider = provider or ASR_PROVIDER
    client = OpenAI(api_key=_api_key, base_url=_api_base)

    max_size = (
        MAX_FILE_SIZE_BYTES_SILICONFLOW
        if _provider == "siliconflow"
        else MAX_FILE_SIZE_BYTES_OPENAI
    )
    audio_size = os.path.getsize(audio_path)

    if audio_size <= max_size:
        return _transcribe_file(client, audio_path, language, _model, _provider)

    size_mb = audio_size / 1024 / 1024
    logger.info(f"Audio file {audio_path} is {size_mb:.1f}MB, splitting")
    return _transcribe_large_file(client, audio_path, language, _model, _provider)


def _transcribe_file(
    client: OpenAI, audio_path: str, language: str, model: str, provider: str
) -> str:
    """Transcribe a single file via the configured ASR provider."""
    with open(audio_path, "rb") as f:
        if provider == "siliconflow":
            transcript = client.audio.transcriptions.create(
                model=model,
                file=f,
            )
            return getattr(transcript, "text", "")

        transcript = client.audio.transcriptions.create(
            model=model,
            file=f,
            language=language,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments = getattr(transcript, "segments", [])
    if segments:
        lines = []
        for seg in segments:
            start = _format_timestamp(seg["start"])
            text = seg["text"].strip()
            if text:
                lines.append(f"[{start}](#t={int(seg['start'])}) {text}")
        return "\n".join(lines)

    return getattr(transcript, "text", "")


def _transcribe_large_file(
    client: OpenAI, audio_path: str, language: str, model: str, provider: str
) -> str:
    """Split a large audio file into chunks and transcribe each."""
    probe_cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    total_seconds = float(result.stdout.strip())

    max_size = (
        MAX_FILE_SIZE_BYTES_SILICONFLOW if provider == "siliconflow" else MAX_FILE_SIZE_BYTES_OPENAI
    )
    ratio = max_size / os.path.getsize(audio_path) * 0.9
    chunk_duration = min(total_seconds * ratio, 600)

    full_transcript_parts = []

    with tempfile.TemporaryDirectory() as tmpdir:
        start = 0.0
        chunk_idx = 0
        while start < total_seconds:
            chunk_path = os.path.join(tmpdir, f"chunk_{chunk_idx}.wav")
            split_cmd = [
                "ffmpeg",
                "-i",
                audio_path,
                "-ss",
                str(start),
                "-t",
                str(chunk_duration),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-y",
                chunk_path,
            ]
            subprocess.run(split_cmd, capture_output=True, check=True)

            text = _transcribe_file(client, chunk_path, language, model, provider)
            if text:
                full_transcript_parts.append(text)

            start += chunk_duration
            chunk_idx += 1

    return "\n".join(full_transcript_parts)


def _format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS timestamp."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
