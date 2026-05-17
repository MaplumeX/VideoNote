"""Audio extraction from video using ffmpeg."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_audio(video_path: str, output_path: str) -> str:
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
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    return output_path


def download_audio_via_ytdlp(url: str, output_dir: str) -> str:
    """Download only the audio stream from a URL using yt-dlp.

    Returns the path to the downloaded WAV file.
    """
    import yt_dlp

    from app.services.subtitle import _ydl_opts

    output_path = str(Path(output_dir) / "audio")

    ydl_opts = _ydl_opts(
        format="bestaudio/best",
        postprocessors=[{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }],
        outtmpl=output_path,
    )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # yt-dlp appends the extension
    wav_path = output_path + ".wav"
    if Path(wav_path).exists():
        return wav_path

    # Fallback: search for any audio file
    audio_files = list(Path(output_dir).glob("audio.*"))
    if audio_files:
        return str(audio_files[0])

    raise FileNotFoundError(f"Audio file not found after yt-dlp download in {output_dir}")
