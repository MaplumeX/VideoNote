"""Audio phase: yt-dlp audio download (URL tasks) + ffmpeg WAV extraction.

Semantics migrated from ``app.services.audio`` (``download_audio_via_ytdlp`` /
``extract_audio``). The WAV target format (pcm_s16le / 16 kHz / mono) is the
ASR-universal format. ``audio_path`` is passed via ``StageResult.extra`` (audio
files are deliberately not artifacts — they must not land in the DB).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import ClassVar

from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages.base import CancelHandleRegistrar, StageContext, StageResult
from app.pipeline.state import PipelinePhase
from app.pipeline.subprocess_util import (
    FFMPEG_BIN,
    build_ytdlp_args,
    run_managed_process,
)

logger = logging.getLogger(__name__)

AUDIO_TIMEOUT_SECONDS = 1200.0
FFMPEG_TIMEOUT_SECONDS = 1200.0

def _cookiefile(ctx: StageContext) -> str | None:
    """The per-user cookie temp file injected by the orchestrator (if any)."""
    path = ctx.extra.get("cookiefile")
    return path if isinstance(path, str) and path else None


async def extract_audio_wav(
    input_path: str,
    output_path: str,
    *,
    register_cancel: CancelHandleRegistrar,
) -> str:
    """Convert an audio/video file to WAV (PCM s16le, 16 kHz, mono) via ffmpeg.

    Migration of ``services.audio.extract_audio``: same ffmpeg arguments,
    now a managed subprocess with cancellation + timeout safety.
    """
    argv = [
        FFMPEG_BIN,
        "-i",
        input_path,
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-y",
        output_path,
    ]
    logger.info("Extracting audio: %s -> %s", input_path, output_path)
    result = await run_managed_process(
        argv,
        register_cancel=register_cancel,
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise PipelineError(
            ErrorCode.AUDIO_EXTRACTION_FAILED,
            detail=f"ffmpeg failed: {result.stderr.strip()[:200]}",
        )
    return output_path


class AudioStage:
    """Download/extract audio; expose the WAV path via ``StageResult.extra``.

    - URL tasks: yt-dlp ``-f bestaudio/best`` then ffmpeg WAV conversion.
    - File (upload) tasks: ffmpeg conversion only.
    """

    phase: ClassVar[PipelinePhase] = PipelinePhase.audio

    async def run(self, ctx: StageContext, *, resume: bool) -> StageResult:
        # No artifact is produced (audio files are not artifacts); resume
        # re-runs the extraction — it is idempotent (deterministic ffmpeg
        # output from the same source).
        input_path = ctx.extra.get("input_path")
        url = ctx.extra.get("url")

        if isinstance(input_path, str) and input_path:
            # File (upload) task: ffmpeg extraction only. Never classify these
            # failures as VIDEO_FETCH_FAILED (legacy rule).
            await ctx.progress.publish(self.phase, 0.0, "Extracting audio")
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_wav = str(Path(tmpdir) / "audio.wav")
                await extract_audio_wav(
                    input_path, tmp_wav, register_cancel=ctx.register_cancel
                )
                wav_path = _persist_wav(tmp_wav, job_id=ctx.job_id)
            await ctx.progress.publish(self.phase, 1.0, "Audio extracted")
            return StageResult(extra={"audio_path": wav_path})

        if isinstance(url, str) and url:
            return await self._run_url(ctx, url)

        raise PipelineError(
            ErrorCode.PROCESSING_FAILED,
            detail="neither url nor input_path in stage context",
        )

    async def _run_url(self, ctx: StageContext, url: str) -> StageResult:
        await ctx.progress.publish(self.phase, 0.0, "Downloading audio")
        with tempfile.TemporaryDirectory() as tmpdir:
            downloaded = await self._download(ctx, url, tmpdir)
            await ctx.progress.publish(self.phase, 0.5, "Converting audio")
            tmp_wav = str(Path(tmpdir) / "audio.wav")
            await extract_audio_wav(
                downloaded, tmp_wav, register_cancel=ctx.register_cancel
            )
            # Keep the WAV alive beyond the TemporaryDirectory scope: the next
            # stage (transcribe) reads it. The orchestrator owns cleanup (C4).
            final_path = _persist_wav(tmp_wav, job_id=ctx.job_id)
        await ctx.progress.publish(self.phase, 1.0, "Audio extracted")
        return StageResult(extra={"audio_path": final_path})

    async def _download(self, ctx: StageContext, url: str, tmpdir: str) -> str:
        """Download the best audio stream via yt-dlp; return the file path."""
        output_path = str(Path(tmpdir) / "audio")
        argv = build_ytdlp_args(
            ["-f", "bestaudio/best", "-o", output_path, url],
            quiet=False,
            cookiefile_path=_cookiefile(ctx),
        )
        result = await run_managed_process(
            argv,
            register_cancel=ctx.register_cancel,
            timeout=AUDIO_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            text = result.stderr or result.stdout
            logger.warning(
                "yt-dlp audio download failed for %s (retcode=%d): %s",
                url,
                result.returncode,
                text.strip()[:500],
            )
            raise PipelineError(
                ErrorCode.VIDEO_FETCH_FAILED,
                detail=f"yt-dlp download failed (retcode={result.returncode})",
            )

        # Find the downloaded file (yt-dlp usually appends an extension, but
        # some extractors produce files without one).
        dir_contents = list(Path(tmpdir).iterdir())
        logger.info(
            "yt-dlp retcode=%d, files in %s: %s",
            result.returncode,
            tmpdir,
            [f.name for f in dir_contents],
        )
        audio_files = [
            f for f in dir_contents if f.name.startswith("audio") and f.name != "audio.wav"
        ]
        if not audio_files:
            raise PipelineError(
                ErrorCode.VIDEO_FETCH_FAILED,
                detail=f"Audio file not found after yt-dlp download in {tmpdir}",
            )
        return str(audio_files[0])


def _persist_wav(wav_path: str, *, job_id: str) -> str:
    """Copy the WAV into a job-scoped temp location that outlives the tmpdir.

    The transcribe stage consumes the file after this stage returns, so it
    cannot live inside the stage-local ``TemporaryDirectory``. The filename is
    job-scoped so concurrent tasks never overwrite each other. The orchestrator
    (C4) removes it after the run.
    """
    dest_dir = Path(tempfile.gettempdir()) / "videonote_pipeline_audio"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{job_id}.wav"
    shutil.move(wav_path, dest)
    return str(dest)
