"""Audio extraction from video using ffmpeg."""

import logging
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_audio(
    video_path: str, output_path: str, *, cancel_event: threading.Event | None = None,
) -> str:
    """Extract audio from a video file as WAV (PCM s16le, 16kHz, mono).

    This format is universally accepted by ASR APIs.
    """
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-y",
        output_path,
    ]

    logger.info(f"Extracting audio: {video_path} -> {output_path}")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    while True:
        try:
            retcode = proc.wait(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if cancel_event is not None and cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise RuntimeError("cancelled") from None

    if retcode != 0:
        _, stderr = proc.communicate()
        raise RuntimeError(f"ffmpeg failed: {stderr.decode() if stderr else ''}")
    return output_path


def download_audio_via_ytdlp(
    url: str, output_dir: str, *, cookiefile_path: str | None = None,
    cancel_event: threading.Event | None = None,
    info: dict | None = None,
) -> str:
    """Download only the audio stream from a URL using yt-dlp.

    Returns the path to the downloaded WAV file.

    If ``info`` is provided (a previously extracted yt-dlp info dict), it is
    reused via ``process_ie_result`` to avoid a redundant ``extract_info``.
    """
    import yt_dlp

    from app.services.subtitle import _ydl_opts

    output_path = str(Path(output_dir) / "audio")

    # Download best audio without FFmpegExtractAudio postprocessor.
    # That postprocessor uses ffprobe to detect the codec and fails on
    # some formats. We convert to WAV separately via extract_audio().
    ydl_opts = _ydl_opts(
        cookiefile_path=cookiefile_path,
        cancel_event=cancel_event,
        format="bestaudio/best",
        outtmpl=output_path,
    )
    # Allow yt-dlp error output through for diagnostics
    ydl_opts["quiet"] = False

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        if info is not None:
            # process_ie_result returns the resolved info dict, NOT a retcode;
            # both paths funnel into __download_wrapper, which records the
            # retcode on the YoutubeDL instance (this is what download() returns).
            ydl.process_ie_result(info, download=True)
        else:
            ydl.download([url])
        retcode = getattr(ydl, "_download_retcode", 0)

    # List directory contents for diagnostics before searching
    dir_contents = list(Path(output_dir).iterdir())
    file_names = [f.name for f in dir_contents]
    logger.info(f"yt-dlp retcode={retcode}, files in {output_dir}: {file_names}")

    if retcode != 0:
        raise RuntimeError(f"yt-dlp download failed (retcode={retcode}) for {url}")

    # Find the downloaded file (yt-dlp usually appends extension, but some
    # extractors produce files without one, e.g. Bilibili combined streams)
    audio_files = [f for f in dir_contents if f.name.startswith("audio") and f.name != "audio.wav"]
    if not audio_files:
        raise FileNotFoundError(f"Audio file not found after yt-dlp download in {output_dir}")

    downloaded = str(audio_files[0])

    # Convert to WAV using ffmpeg directly (more reliable than yt-dlp's postprocessor)
    wav_path = str(Path(output_dir) / "audio.wav")
    extract_audio(downloaded, wav_path, cancel_event=cancel_event)
    return wav_path
