"""yt-dlp subtitle extraction for YouTube and Bilibili."""

import logging
import re
import tempfile
import uuid
from pathlib import Path

import httpx
import yt_dlp

from app.config import UPLOAD_DIR, YT_DLP_COOKIES_FILE, YT_DLP_COOKIES_FROM_BROWSER, YT_DLP_PROXY

logger = logging.getLogger(__name__)


def _parse_cookies_from_browser(value: str) -> tuple[str, str | None, str | None, str | None]:
    mobj = re.fullmatch(
        r"""(?x)
        (?P<name>[^+:]+)
        (?:\s*\+\s*(?P<keyring>[^:]+))?
        (?:\s*:\s*(?!:)(?P<profile>.+?))?
        (?:\s*::\s*(?P<container>.+))?
        """,
        value,
    )
    if mobj is None:
        raise ValueError(f"Invalid YT_DLP_COOKIES_FROM_BROWSER value: {value}")

    browser_name, keyring, profile, container = mobj.group(
        "name", "keyring", "profile", "container"
    )
    return browser_name.lower(), profile, keyring.upper() if keyring else None, container


def _ydl_opts(
    *,
    cookiefile_path: str | None = None,
    **extra: object,
) -> dict:
    opts: dict = {"quiet": True, "no_warnings": True, "remote_components": ["ejs:github"], **extra}
    if YT_DLP_PROXY:
        opts["proxy"] = YT_DLP_PROXY
    # Per-user cookie file takes priority
    if cookiefile_path:
        opts["cookiefile"] = cookiefile_path
    else:
        if YT_DLP_COOKIES_FROM_BROWSER:
            opts["cookiesfrombrowser"] = _parse_cookies_from_browser(YT_DLP_COOKIES_FROM_BROWSER)
        if YT_DLP_COOKIES_FILE:
            opts["cookiefile"] = YT_DLP_COOKIES_FILE
    return opts


def extract_subtitles(
    url: str, languages: list[str] | None = None, *, cookiefile_path: str | None = None
) -> str | None:
    """Extract subtitles from a video URL using yt-dlp.

    Tries manual subtitles first, then auto-generated captions.
    Returns SRT-formatted subtitle text, or None if no subtitles found.
    """
    if languages is None:
        languages = ["en", "zh-Hans", "zh", "ja"]

    ydl_opts = _ydl_opts(
        cookiefile_path=cookiefile_path,
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
                                url, lang, auto=False, languages=languages,
                                cookiefile_path=cookiefile_path,
                            )

            # Try auto-generated captions
            auto_captions = info.get("automatic_captions", {})
            for lang in languages:
                if lang in auto_captions:
                    return _download_and_read_subtitle(
                        url, lang, auto=True, languages=languages,
                        cookiefile_path=cookiefile_path,
                    )

            logger.info(f"No subtitles found for {url}")
            return None

    except Exception as e:
        logger.warning(f"Subtitle extraction failed for {url}: {e}")
        return None


def _download_and_read_subtitle(
    url: str, lang: str, auto: bool, languages: list[str],
    *, cookiefile_path: str | None = None,
) -> str | None:
    """Download subtitle file via yt-dlp and read its content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = _ydl_opts(
            cookiefile_path=cookiefile_path,
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


def get_video_title(url: str, *, cookiefile_path: str | None = None) -> str | None:
    """Get the title of a video from its URL using yt-dlp."""
    ydl_opts = _ydl_opts(cookiefile_path=cookiefile_path)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title") if info else None
    except Exception as e:
        logger.warning(f"Failed to get video title for {url}: {e}")
        return None


def get_video_info(url: str, *, cookiefile_path: str | None = None) -> dict:
    """Get video metadata (title, thumbnail) from its URL using yt-dlp.

    Returns a dict with keys 'title' (str | None) and 'thumbnail_url' (str | None).
    """
    ydl_opts = _ydl_opts(cookiefile_path=cookiefile_path)
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


def download_thumbnail(url: str) -> str | None:
    """Download a thumbnail image to UPLOAD_DIR/thumbnails/.

    For Bilibili URLs, sets Referer header to bypass anti-hotlinking.
    Returns the local filename on success, None on failure.
    """
    if not url:
        return None

    headers: dict = {}
    if "bilibili.com" in url or "b23.tv" in url or "hdslb.com" in url:
        headers["Referer"] = "https://www.bilibili.com"

    proxies = None
    if YT_DLP_PROXY:
        proxies = YT_DLP_PROXY

    try:
        with httpx.Client(proxy=proxies, follow_redirects=True, timeout=15) as client:
            resp = client.get(url, headers=headers)
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
    except Exception as e:
        logger.warning(f"Failed to download thumbnail {url}: {e}")
        return None
