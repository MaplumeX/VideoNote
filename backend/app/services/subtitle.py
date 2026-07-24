"""yt-dlp subtitle extraction for YouTube and Bilibili."""

import logging
import re
import tempfile
import threading
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
    cancel_event: threading.Event | None = None,
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
    if cancel_event is not None:
        def _cancel_hook(d: dict) -> None:
            if cancel_event.is_set():
                raise yt_dlp.utils.DownloadCancelled("Cancelled by user")
        hooks = opts.get("progress_hooks", [])
        hooks.append(_cancel_hook)
        opts["progress_hooks"] = hooks
    return opts


# Matches SRT (HH:MM:SS,mmm) and VTT (HH:MM:SS.mmm) timestamp ranges.
_TIMESTAMP_RANGE_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
    r"\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def _srt_to_transcript(raw: str) -> str | None:
    """Convert SRT/VTT subtitle text into ``[HH:MM:SS](#t=SECONDS) text`` lines.

    Returns None when no valid cue blocks are found so the pipeline can fall
    back to ASR.
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


def extract_subtitles(
    url: str, languages: list[str] | None = None, *, cookiefile_path: str | None = None,
    cancel_event: threading.Event | None = None,
) -> str | None:
    """Extract subtitles from a video URL using yt-dlp.

    Tries manual subtitles first, then auto-generated captions.
    Returns SRT-formatted subtitle text, or None if no subtitles found.
    """
    if languages is None:
        languages = ["en", "zh-Hans", "zh", "ja"]

    ydl_opts = _ydl_opts(
        cookiefile_path=cookiefile_path,
        cancel_event=cancel_event,
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
                                cancel_event=cancel_event,
                            )

            # Try auto-generated captions
            auto_captions = info.get("automatic_captions", {})
            for lang in languages:
                if lang in auto_captions:
                    return _download_and_read_subtitle(
                        url, lang, auto=True, languages=languages,
                        cookiefile_path=cookiefile_path,
                        cancel_event=cancel_event,
                    )

            logger.info(f"No subtitles found for {url}")
            return None

    except Exception as e:
        logger.warning(f"Subtitle extraction failed for {url}: {e}")
        return None


def _download_and_read_subtitle(
    url: str, lang: str, auto: bool, languages: list[str],
    *, cookiefile_path: str | None = None,
    cancel_event: threading.Event | None = None,
) -> str | None:
    """Download subtitle file via yt-dlp and read its content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = _ydl_opts(
            cookiefile_path=cookiefile_path,
            cancel_event=cancel_event,
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
                return _srt_to_transcript(srt_files[0].read_text(encoding="utf-8"))

            # Try .vtt files (some platforms don't convert properly)
            vtt_files = list(Path(tmpdir).glob("*.vtt"))
            if vtt_files:
                return _srt_to_transcript(vtt_files[0].read_text(encoding="utf-8"))

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


def classify_ytdlp_error(exc: Exception) -> str:
    """Map a yt-dlp / download exception to a stable error code.

    The returned code is one of ``VIDEO_PRIVATE``, ``VIDEO_GEO_RESTRICTED``,
    ``VIDEO_NOT_FOUND``, ``VIDEO_COOKIE_INVALID``, or ``VIDEO_FETCH_FAILED``
    (the catch-all fallback).
    """
    msg = str(exc).lower()
    if "private" in msg or "login required" in msg:
        return "VIDEO_PRIVATE"
    if "geo" in msg or "not available in your country" in msg or "region" in msg:
        return "VIDEO_GEO_RESTRICTED"
    if "404" in msg or "not found" in msg or "unavailable" in msg or "deleted" in msg:
        return "VIDEO_NOT_FOUND"
    if "cookie" in msg or ("login" in msg and "required" in msg):
        return "VIDEO_COOKIE_INVALID"
    return "VIDEO_FETCH_FAILED"


def get_video_info_strict(
    url: str, *, cookiefile_path: str | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Like :func:`get_video_info` but raises on failure with a classified error code.

    The raised exception has a ``code`` attribute set to the stable error code
    (e.g. ``VIDEO_PRIVATE``), falling back to ``VIDEO_FETCH_FAILED``.
    """
    ydl_opts = _ydl_opts(cookiefile_path=cookiefile_path, cancel_event=cancel_event)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise RuntimeError("yt-dlp returned no info")
            return {"title": info.get("title"), "thumbnail_url": info.get("thumbnail")}
    except Exception as e:
        code = classify_ytdlp_error(e)
        err = RuntimeError(f"{code}: {e}")
        err.code = code
        raise err from e


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
