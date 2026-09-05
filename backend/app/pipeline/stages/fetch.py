"""Fetching phase: video metadata via the yt-dlp CLI + async thumbnail download.

Semantics migrated from ``app.services/subtitle.py`` (``get_video_info_strict``
and ``download_thumbnail``). The Python API is replaced by a managed yt-dlp
subprocess running ``--dump-json``; the historical ``process_ie_result`` misuse
class of bugs is structurally impossible here (that call path no longer exists).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import ClassVar

import httpx

from app.config import UPLOAD_DIR, YT_DLP_PROXY
from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages.base import StageContext, StageResult
from app.pipeline.state import ArtifactKind, PipelinePhase
from app.pipeline.subprocess_util import (
    build_ytdlp_args,
    classify_ytdlp_error,
    run_managed_process,
)

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 120.0
THUMBNAIL_TIMEOUT_SECONDS = 15.0


@dataclass
class VideoMeta:
    """``video_meta`` artifact content (persisted by the orchestrator)."""

    title: str | None
    thumbnail: str | None  # local filename under UPLOAD_DIR/thumbnails


class FetchStage:
    """Fetch video title + thumbnail for a URL task."""

    phase: ClassVar[PipelinePhase] = PipelinePhase.fetching

    async def run(self, ctx: StageContext, *, resume: bool) -> StageResult:
        existing = await ctx.artifacts.get(ArtifactKind.video_meta)
        if resume and isinstance(existing, VideoMeta):
            return StageResult(outputs={ArtifactKind.video_meta: existing})

        url = self._source_url(ctx)
        await ctx.progress.publish(self.phase, 0.0, "Fetching video info")
        info = await self._dump_json(ctx, url)

        title = info.get("title")
        thumbnail_filename = await self._download_thumbnail(info.get("thumbnail"))
        await ctx.progress.publish(self.phase, 1.0, "Video info fetched")
        return StageResult(
            outputs={ArtifactKind.video_meta: VideoMeta(title, thumbnail_filename)}
        )

    def _source_url(self, ctx: StageContext) -> str:
        # The URL is injected by the orchestrator via StageContext.extra (C4).
        url = ctx.extra.get("url")
        if not isinstance(url, str) or not url:
            raise PipelineError(
                ErrorCode.PROCESSING_FAILED, detail="url missing from stage context"
            )
        return url

    async def _dump_json(self, ctx: StageContext, url: str) -> dict:
        argv = build_ytdlp_args(["--dump-json", "--no-download", url])
        result = await run_managed_process(
            argv,
            register_cancel=ctx.register_cancel,
            timeout=FETCH_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            text = result.stderr or result.stdout
            code = classify_ytdlp_error(text)
            logger.warning(
                "yt-dlp metadata fetch failed for %s (retcode=%d): %s",
                url,
                result.returncode,
                text.strip()[:500],
            )
            raise PipelineError(code)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise PipelineError(
                ErrorCode.VIDEO_FETCH_FAILED, detail="yt-dlp returned invalid JSON"
            ) from e

    async def _download_thumbnail(self, url: str | None) -> str | None:
        """Download the thumbnail; failure is non-fatal (None + warning)."""
        if not url:
            return None
        try:
            return await download_thumbnail(url)
        except Exception as e:
            logger.warning("Failed to download thumbnail %s: %s", url, e)
            return None


async def download_thumbnail(url: str) -> str | None:
    """Download a thumbnail image to ``UPLOAD_DIR/thumbnails`` (async, non-fatal).

    Bilibili's CDN enforces Referer-based anti-hotlinking; set the Referer
    header for Bilibili URLs (legacy semantics preserved). Returns the local
    filename on success.
    """
    headers: dict[str, str] = {}
    if "bilibili.com" in url or "b23.tv" in url or "hdslb.com" in url:
        headers["Referer"] = "https://www.bilibili.com"

    proxies = YT_DLP_PROXY or None
    async with httpx.AsyncClient(
        proxy=proxies, follow_redirects=True, timeout=THUMBNAIL_TIMEOUT_SECONDS
    ) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        ext = ".jpg"
        if "webp" in content_type:
            ext = ".webp"
        elif "png" in content_type:
            ext = ".png"

        thumb_dir = UPLOAD_DIR / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{uuid.uuid4().hex}{ext}"
        (thumb_dir / filename).write_bytes(resp.content)
        return filename
