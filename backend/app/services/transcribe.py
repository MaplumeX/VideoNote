"""Transcription via OpenAI Whisper API."""

import logging
import os
import subprocess
import tempfile

from openai import OpenAI

from app.config import ASR_API_BASE, ASR_API_KEY, ASR_MODEL

logger = logging.getLogger(__name__)

# Whisper API has a 25MB file size limit
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024


def transcribe_audio(audio_path: str, language: str = "zh") -> str:
    """Transcribe an audio file using OpenAI Whisper API.

    Handles the 25MB limit by splitting large files.
    Returns the full transcript text.
    """
    client = OpenAI(api_key=ASR_API_KEY, base_url=ASR_API_BASE)

    audio_size = os.path.getsize(audio_path)

    if audio_size <= MAX_FILE_SIZE_BYTES:
        return _transcribe_file(client, audio_path, language)

    # Split large audio into chunks
    size_mb = audio_size / 1024 / 1024
    logger.info(f"Audio file {audio_path} is {size_mb:.1f}MB, splitting")
    return _transcribe_large_file(client, audio_path, language)


def _transcribe_file(client: OpenAI, audio_path: str, language: str) -> str:
    """Transcribe a single file via Whisper API."""
    with open(audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model=ASR_MODEL,
            file=f,
            language=language,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    # Build text with timestamps
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
    client: OpenAI, audio_path: str, language: str
) -> str:
    """Split a large audio file into chunks and transcribe each."""
    # Get audio duration
    probe_cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    total_seconds = float(result.stdout.strip())

    # Calculate chunk duration based on file size ratio
    ratio = MAX_FILE_SIZE_BYTES / os.path.getsize(audio_path) * 0.9
    chunk_duration = min(total_seconds * ratio, 600)  # Max 10 min

    full_transcript_parts = []

    with tempfile.TemporaryDirectory() as tmpdir:
        start = 0.0
        chunk_idx = 0
        while start < total_seconds:
            chunk_path = os.path.join(tmpdir, f"chunk_{chunk_idx}.wav")
            split_cmd = [
                "ffmpeg",
                "-i", audio_path,
                "-ss", str(start),
                "-t", str(chunk_duration),
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-y", chunk_path,
            ]
            subprocess.run(split_cmd, capture_output=True, check=True)

            text = _transcribe_file(client, chunk_path, language)
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
