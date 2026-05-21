"""yt-dlp subtitle extraction for YouTube and Bilibili."""

import logging
import tempfile
from pathlib import Path

import yt_dlp

from app.config import YT_DLP_PROXY

logger = logging.getLogger(__name__)


def _ydl_opts(**extra: object) -> dict:
    opts: dict = {"quiet": True, "no_warnings": True, **extra}
    if YT_DLP_PROXY:
        opts["proxy"] = YT_DLP_PROXY
    return opts


def extract_subtitles(url: str, languages: list[str] | None = None) -> str | None:
    """Extract subtitles from a video URL using yt-dlp.

    Tries manual subtitles first, then auto-generated captions.
    Returns SRT-formatted subtitle text, or None if no subtitles found.
    """
    if languages is None:
        languages = ["en", "zh-Hans", "zh", "ja"]

    ydl_opts = _ydl_opts(
        writesubtitles=True,
        writeautomaticsub=True,
        subtitleslangs=languages,
        subtitlesformat="srt",
        convertsubs="srt",
    )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return None

            # Try manual subtitles first
            subtitles = info.get("subtitles", {})
            for lang in languages:
                if lang in subtitles:
                    subs = subtitles[lang]
                    for sub_info in subs:
                        if sub_info.get("ext") == "srt":
                            # yt-dlp with download=False doesn't get the
                            # actual content, need to re-run with download
                            return _download_and_read_subtitle(
                                url, lang, auto=False, languages=languages
                            )

            # Try auto-generated captions
            auto_captions = info.get("automatic_captions", {})
            for lang in languages:
                if lang in auto_captions:
                    return _download_and_read_subtitle(
                        url, lang, auto=True, languages=languages
                    )

            logger.info(f"No subtitles found for {url}")
            return None

    except Exception as e:
        logger.warning(f"Subtitle extraction failed for {url}: {e}")
        return None


def _download_and_read_subtitle(
    url: str, lang: str, auto: bool, languages: list[str]
) -> str | None:
    """Download subtitle file via yt-dlp and read its content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = _ydl_opts(
            writesubtitles=not auto,
            writeautomaticsub=auto,
            subtitleslangs=[lang],
            subtitlesformat="srt",
            convertsubs="srt",
            outtmpl=str(Path(tmpdir) / "%(id)s"),
            skip_download=True,
        )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Find the .srt file in tmpdir
            srt_files = list(Path(tmpdir).glob("*.srt"))
            if srt_files:
                return srt_files[0].read_text(encoding="utf-8")

            # Try .vtt files (some platforms don't convert properly)
            vtt_files = list(Path(tmpdir).glob("*.vtt"))
            if vtt_files:
                return vtt_files[0].read_text(encoding="utf-8")

            return None
        except Exception as e:
            logger.warning(f"Subtitle download failed: {e}")
            return None


def detect_video_platform(url: str) -> str:
    """Detect whether a URL is from YouTube or Bilibili."""
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "bilibili.com" in url or "b23.tv" in url:
        return "bilibili"
    return "unknown"


def get_video_title(url: str) -> str | None:
    """Get the title of a video from its URL using yt-dlp."""
    ydl_opts = _ydl_opts()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title") if info else None
    except Exception as e:
        logger.warning(f"Failed to get video title for {url}: {e}")
        return None


def get_video_info(url: str) -> dict:
    """Get video metadata (title, thumbnail) from its URL using yt-dlp.

    Returns a dict with keys 'title' (str | None) and 'thumbnail_url' (str | None).
    """
    ydl_opts = _ydl_opts()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return {"title": None, "thumbnail_url": None}
            return {
                "title": info.get("title"),
                "thumbnail_url": info.get("thumbnail"),
            }
    except Exception as e:
        logger.warning(f"Failed to get video info for {url}: {e}")
        return {"title": None, "thumbnail_url": None}
