"""Subtitle phase: yt-dlp CLI subtitle download + pure SRT/VTT parsing.

Semantics migrated from ``app.services.subtitle`` (``extract_subtitles`` /
``_srt_to_transcript``): language priority by note language, VTT NOTE/WEBVTT
header skipping, timestamp-line locating, ``[HH:MM:SS](#t=SECONDS)`` output,
empty-cue dropping, and the no-cue -> None fallback (miss -> empty outputs so
the orchestrator routes to the audio branch per the transition table).
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import ClassVar

from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages.base import StageContext, StageResult
from app.pipeline.state import ArtifactKind, PipelinePhase
from app.pipeline.subprocess_util import (
    build_ytdlp_args,
    classify_ytdlp_error,
    run_managed_process,
)

logger = logging.getLogger(__name__)

SUBTITLE_TIMEOUT_SECONDS = 300.0

def _cookiefile(ctx: StageContext) -> str | None:
    """The per-user cookie temp file injected by the orchestrator (if any)."""
    path = ctx.extra.get("cookiefile")
    return path if isinstance(path, str) and path else None

# Matches SRT (HH:MM:SS,mmm) and VTT (HH:MM:SS.mmm) timestamp ranges.
_TIMESTAMP_RANGE_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
    r"\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def subtitle_languages(note_lang: str) -> list[str]:
    """Reorder subtitle language preference based on the note language.

    Migration of ``routes._subtitle_languages``.
    """
    if note_lang.startswith("zh"):
        return ["zh-Hans", "zh", "en", "ja"]
    return ["en", "zh-Hans", "zh", "ja"]


def parse_srt_or_vtt(raw: str) -> str | None:
    """Convert SRT/VTT subtitle text into ``[HH:MM:SS](#t=SECONDS) text`` lines.

    Returns None when no valid cue blocks are found so the pipeline can fall
    back to ASR. (Full migration of the legacy ``_srt_to_transcript``.)
    """
    if not raw or not raw.strip():
        return None

    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # Split into blocks separated by blank lines
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip() == "":
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)

    result_lines: list[str] = []
    for block in blocks:
        # Skip VTT header and NOTE blocks
        if block[0].strip().startswith("WEBVTT") or block[0].strip().startswith("NOTE"):
            continue

        # Find the timestamp line within the block
        match: re.Match[str] | None = None
        ts_idx = -1
        for i, line in enumerate(block):
            m = _TIMESTAMP_RANGE_RE.search(line)
            if m:
                match = m
                ts_idx = i
                break

        if match is None:
            continue

        h, m, s, ms = (
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4)),
        )
        total_seconds = h * 3600 + m * 60 + s + ms / 1000.0

        # Text lines are everything after the timestamp line
        text = " ".join(
            stripped for line in block[ts_idx + 1 :] if (stripped := line.strip())
        )
        if not text:
            continue

        ts_str = f"{h:02d}:{m:02d}:{s:02d}"
        result_lines.append(f"[{ts_str}](#t={int(total_seconds)}) {text}")

    if not result_lines:
        return None
    return "\n".join(result_lines)


class SubtitleStage:
    """Extract subtitles for a URL task; miss -> empty outputs (audio fallback)."""

    phase: ClassVar[PipelinePhase] = PipelinePhase.subtitle

    async def run(self, ctx: StageContext, *, resume: bool) -> StageResult:
        existing = await ctx.artifacts.get(ArtifactKind.subtitle)
        if resume and isinstance(existing, str) and existing:
            return StageResult(outputs={ArtifactKind.subtitle: existing})

        url = self._source_url(ctx)
        await ctx.progress.publish(self.phase, 0.0, "Extracting subtitles")

        transcript = await self._extract(ctx, url)
        await ctx.progress.publish(self.phase, 1.0, "Subtitles extracted")
        if transcript is None:
            # Miss: no artifact written; the orchestrator routes to the audio
            # branch via the transition table (subtitle -> audio).
            return StageResult()
        return StageResult(outputs={ArtifactKind.subtitle: transcript})

    def _source_url(self, ctx: StageContext) -> str:
        url = ctx.extra.get("url")
        if not isinstance(url, str) or not url:
            raise PipelineError(
                ErrorCode.PROCESSING_FAILED, detail="url missing from stage context"
            )
        return url

    async def _extract(self, ctx: StageContext, url: str) -> str | None:
        """Run yt-dlp to download subtitle files; return parsed text or None.

        None means "no subtitles found" (miss -> audio fallback). A yt-dlp
        failure (nonzero retcode) raises with the last real stderr line as the
        detail (sanitized at ``PipelineError`` construction).
        """
        languages = subtitle_languages(ctx.language)
        with tempfile.TemporaryDirectory() as tmpdir:
            argv = build_ytdlp_args(
                [
                    "--write-subs",
                    "--write-auto-subs",
                    "--sub-format",
                    "srt",
                    "--convert-subs",
                    "srt",
                    "--sub-langs",
                    ",".join(languages),
                    "--skip-download",
                    "-o",
                    str(Path(tmpdir) / "%(id)s"),
                    url,
                ],
                cookiefile_path=_cookiefile(ctx),
            )
            result = await run_managed_process(
                argv,
                register_cancel=ctx.register_cancel,
                timeout=SUBTITLE_TIMEOUT_SECONDS,
            )
            if result.returncode != 0:
                text = result.stderr or result.stdout
                # Classify for logging fidelity; the subtitle stage keeps its
                # own error code (a download failure here falls back nowhere).
                _code = classify_ytdlp_error(text)
                logger.warning(
                    "Subtitle extraction failed for %s (retcode=%d, classified=%s): %s",
                    url,
                    result.returncode,
                    _code.value,
                    text.strip()[:500],
                )
                last = _last_error_line(text)
                raise PipelineError(
                    ErrorCode.SUBTITLE_EXTRACTION_FAILED,
                    detail=last or f"yt-dlp failed (retcode={result.returncode})",
                )

            # Collect subtitle files, sorted by language priority (the
            # requested order mirrors the CLI --sub-langs order).
            all_subs: list[Path] = []
            for ext in ("*.srt", "*.vtt"):
                all_subs.extend(Path(tmpdir).glob(ext))

            def _lang_priority(filepath: Path) -> int:
                for i, lang in enumerate(languages):
                    if lang in filepath.stem:
                        return i
                return len(languages)

            all_subs.sort(key=_lang_priority)

            for f in all_subs:
                content = parse_srt_or_vtt(f.read_text(encoding="utf-8"))
                if content:
                    return content

            logger.info("No subtitles found for %s", url)
            return None

def _last_error_line(text: str) -> str:
    """Return the last non-empty (stripped) line of a yt-dlp error output.

    Mirrors ``stages.audio._last_error_line``; ``PipelineError`` sanitizes the
    detail at construction, so no manual sanitization here.
    """
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""
