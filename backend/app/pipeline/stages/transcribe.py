"""Transcribe phase: Async [OI] ASR with large-file chunking and stitching.

Semantics migrated from ``app.services.transcribe``: file-size limits (25 MB
OpenAI-compatible / 50 MB SiliconFlow), ffprobe duration probe + ffmpeg chunk
splitting, per-chunk timestamp offsetting (``_shift_timestamps``), the
SiliconFlow plain-text branch, and the note-language -> Whisper language
mapping. The sync ``[OI]`` client is replaced by ``AsyncOpenAI`` so cancellation
aborts in-flight HTTP requests immediately.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from typing import ClassVar, Protocol

from openai import AsyncOpenAI

from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages.base import (
    ProviderEndpoint,
    StageContext,
    StageResult,
)
from app.pipeline.state import ArtifactKind, PipelinePhase
from app.pipeline.subprocess_util import (
    FFMPEG_BIN,
    FFPROBE_BIN,
    run_managed_process,
)

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES_OPENAI = 25 * 1024 * 1024
MAX_FILE_SIZE_BYTES_SILICONFLOW = 50 * 1024 * 1024

PROBE_TIMEOUT_SECONDS = 60.0
FFMPEG_TIMEOUT_SECONDS = 1200.0
# Lower bound for the chunk duration when splitting oversized audio (module-level
# so tests can shrink it without replacing the splitting loop itself).
MIN_CHUNK_DURATION_SECONDS = 30.0

# Note-language -> Whisper language mapping (legacy ``routes._asr_language``):
# unmapped languages return None so Whisper auto-detects.
_ASR_LANG_MAP = {"zh-CN": "zh", "en": "en", "ja": "ja"}


def asr_language(note_lang: str) -> str | None:
    """Map a note-language code to a Whisper language code."""
    return _ASR_LANG_MAP.get(note_lang)


# Matches the machine-generated `[HH:MM:SS](#t=SECONDS)` timestamp prefix.
_TS_LINE_RE = re.compile(r"\[(\d{1,2}):(\d{2}):(\d{2})\]\(#t=(\d+)\)")


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def shift_timestamps(text: str, offset_seconds: float) -> str:
    """Shift every leading ``[HH:MM:SS](#t=SECONDS)`` timestamp by an offset.

    Migration of ``services.transcribe._shift_timestamps``: each chunk's segment
    times are relative to the chunk start, so the chunk's start offset is added
    before joining. Lines without a timestamp are returned unchanged.
    """
    if offset_seconds == 0:
        return text

    def _replace(match: re.Match[str]) -> str:
        h, m, s = int(match[1]), int(match[2]), int(match[3])
        display_seconds = h * 3600 + m * 60 + s + offset_seconds
        jump_seconds = int(int(match[4]) + offset_seconds)
        return f"[{format_timestamp(display_seconds)}](#t={jump_seconds})"

    out_lines = []
    for line in text.splitlines():
        # Only replace the leading timestamp so incidental bracketed text in
        # the segment body is untouched.
        out_lines.append(_TS_LINE_RE.sub(_replace, line, count=1))
    return "\n".join(out_lines)


class TranscriptionClient(Protocol):
    """The slice of ``AsyncOpenAI`` this stage depends on (injectable in tests)."""

    async def transcribe(  # type: ignore[no-untyped-def]
        self,
        *,
        model: str,
        file_path: str,
        language: str | None,
        provider: str,
    ) -> str:
        """Transcribe one audio file; returns the provider-specific text."""


class _AsyncOpenAIAdapter:
    """Adapts ``AsyncOpenAI.audio.transcriptions`` to ``TranscriptionClient``."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def transcribe(
        self,
        *,
        model: str,
        file_path: str,
        language: str | None,
        provider: str,
    ) -> str:
        with open(file_path, "rb") as f:
            if provider == "siliconflow":
                transcript = await self._client.audio.transcriptions.create(
                    model=model,
                    file=f,
                )
                return getattr(transcript, "text", "")

            kwargs: dict = {
                "model": model,
                "file": f,
                "response_format": "verbose_json",
                "timestamp_granularities": ["segment"],
            }
            if language is not None:
                kwargs["language"] = language
            transcript = await self._client.audio.transcriptions.create(**kwargs)

        segments = getattr(transcript, "segments", [])
        if segments:
            lines = []
            for seg in segments:
                start = format_timestamp(seg["start"])
                text = seg["text"].strip()
                if text:
                    lines.append(f"[{start}](#t={int(seg['start'])}) {text}")
            return "\n".join(lines)

        return getattr(transcript, "text", "")


class TranscribeStage:
    """Transcribe the extracted audio into a ``transcript`` artifact."""

    phase: ClassVar[PipelinePhase] = PipelinePhase.transcribe

    async def run(self, ctx: StageContext, *, resume: bool) -> StageResult:
        existing = await ctx.artifacts.get(ArtifactKind.transcript)
        if resume and isinstance(existing, str) and existing:
            return StageResult(outputs={ArtifactKind.transcript: existing})

        endpoint = ctx.provider.asr
        if not endpoint.is_complete():
            raise PipelineError(ErrorCode.PROVIDER_NOT_CONFIGURED)

        audio_path = ctx.extra.get("audio_path")
        if not isinstance(audio_path, str) or not audio_path:
            raise PipelineError(
                ErrorCode.PROCESSING_FAILED, detail="audio_path missing from stage context"
            )

        await ctx.progress.publish(self.phase, 0.0, "Transcribing audio")
        try:
            transcript = await self._transcribe(ctx, audio_path)
        except PipelineError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # ASR failures (incl. network errors surfacing through the SDK)
            # map to the stable stage code; raw text stays in the log only.
            logger.warning("Transcription failed for %s: %s", ctx.job_id, e)
            raise PipelineError(
                ErrorCode.TRANSCRIPTION_FAILED, detail=str(e), cause=e
            ) from e
        await ctx.progress.publish(self.phase, 1.0, "Transcription complete")
        return StageResult(outputs={ArtifactKind.transcript: transcript})

    async def _transcribe(self, ctx: StageContext, audio_path: str) -> str:
        """Dispatch to single-file or chunked transcription (legacy semantics)."""
        endpoint = ctx.provider.asr
        language = asr_language(ctx.language)
        client = self._build_client(endpoint)

        max_size = (
            MAX_FILE_SIZE_BYTES_SILICONFLOW
            if endpoint.provider == "siliconflow"
            else MAX_FILE_SIZE_BYTES_OPENAI
        )
        audio_size = os.path.getsize(audio_path)

        if audio_size <= max_size:
            return await client.transcribe(
                model=endpoint.model,
                file_path=audio_path,
                language=language,
                provider=endpoint.provider,
            )

        size_mb = audio_size / 1024 / 1024
        logger.info("Audio file %s is %.1fMB, splitting", audio_path, size_mb)
        return await self._transcribe_large(ctx, client, audio_path, language, endpoint)

    def _build_client(self, endpoint: ProviderEndpoint) -> TranscriptionClient:
        """Build the ASR client from the endpoint config (override point for tests)."""
        client = AsyncOpenAI(api_key=endpoint.api_key, base_url=endpoint.api_base)
        return _AsyncOpenAIAdapter(client)

    async def _transcribe_large(
        self,
        ctx: StageContext,
        client: TranscriptionClient,
        audio_path: str,
        language: str | None,
        endpoint: ProviderEndpoint,
    ) -> str:
        """Split an oversized audio file into chunks and transcribe each."""
        total_seconds = await self._probe_duration(ctx, audio_path)
        max_size = (
            MAX_FILE_SIZE_BYTES_SILICONFLOW
            if endpoint.provider == "siliconflow"
            else MAX_FILE_SIZE_BYTES_OPENAI
        )
        ratio = max_size / os.path.getsize(audio_path) * 0.9
        chunk_duration = max(
            min(total_seconds * ratio, 600), MIN_CHUNK_DURATION_SECONDS
        )

        parts: list[str] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            start = 0.0
            chunk_idx = 0
            while start < total_seconds:
                chunk_path = os.path.join(tmpdir, f"chunk_{chunk_idx}.wav")
                await self._split_chunk(ctx, audio_path, start, chunk_duration, chunk_path)
                text = await client.transcribe(
                    model=endpoint.model,
                    file_path=chunk_path,
                    language=language,
                    provider=endpoint.provider,
                )
                if text:
                    parts.append(shift_timestamps(text, start))
                chunk_idx += 1
                await ctx.progress.publish(
                    self.phase,
                    min(start / total_seconds, 1.0),
                    f"Transcribing chunk {chunk_idx}...",
                )
                start += chunk_duration

        return "\n".join(parts)

    async def _probe_duration(self, ctx: StageContext, audio_path: str) -> float:
        argv = [
            FFPROBE_BIN,
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        result = await run_managed_process(
            argv,
            register_cancel=ctx.register_cancel,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise PipelineError(
                ErrorCode.TRANSCRIPTION_FAILED,
                detail=f"ffprobe failed: {result.stderr.strip()[:200]}",
            )
        try:
            total_seconds = float(result.stdout.strip())
        except ValueError as e:
            raise PipelineError(
                ErrorCode.TRANSCRIPTION_FAILED,
                detail=f"ffprobe returned invalid duration: {result.stdout!r}",
            ) from e
        if total_seconds <= 0:
            raise PipelineError(
                ErrorCode.TRANSCRIPTION_FAILED,
                detail=f"Invalid audio duration: {total_seconds}",
            )
        return total_seconds

    async def _split_chunk(
        self,
        ctx: StageContext,
        audio_path: str,
        start: float,
        duration: float,
        chunk_path: str,
    ) -> None:
        argv = [
            FFMPEG_BIN,
            "-i",
            audio_path,
            "-ss",
            str(start),
            "-t",
            str(duration),
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
        result = await run_managed_process(
            argv,
            register_cancel=ctx.register_cancel,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise PipelineError(
                ErrorCode.TRANSCRIPTION_FAILED,
                detail=f"ffmpeg chunk split failed: {result.stderr.strip()[:200]}",
            )
