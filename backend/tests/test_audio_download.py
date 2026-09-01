"""Tests for download_audio_via_ytdlp retcode handling (P0-1)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import audio


class _FakeYoutubeDL:
    """Stand-in for yt_dlp.YoutubeDL."""

    def __init__(self, opts: dict, *, retcode: int, write_file: bool):
        self._opts = opts
        self._download_retcode = retcode
        self._write_file = write_file

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def process_ie_result(self, info: dict, download: bool = False) -> dict:
        assert download is True
        if self._write_file:
            outtmpl = str(self._opts["outtmpl"])
            Path(outtmpl + ".webm").write_bytes(b"fake audio data")
        return info  # the real API returns the resolved info dict, NOT a retcode

    def download(self, urls: list[str]) -> int:
        return self._download_retcode


def test_info_reuse_success(tmp_path: Path) -> None:
    """process_ie_result returning a dict must not be treated as a nonzero retcode."""

    def fake_ydl_factory(opts: dict) -> _FakeYoutubeDL:
        return _FakeYoutubeDL(opts, retcode=0, write_file=True)

    with (
        patch("yt_dlp.YoutubeDL", fake_ydl_factory),
        patch.object(audio, "extract_audio", side_effect=None) as mock_extract,
    ):
        mock_extract.side_effect = (
            lambda downloaded, wav_path, cancel_event=None: wav_path
        )
        wav_path = audio.download_audio_via_ytdlp(
            "https://www.youtube.com/watch?v=abcdefghijk",
            str(tmp_path),
            info={"id": "abcdefghijk", "title": "test"},
        )

    assert wav_path == str(tmp_path / "audio.wav")
    mock_extract.assert_called_once()


def test_download_retcode_failure_raises(tmp_path: Path) -> None:
    """A nonzero _download_retcode must raise RuntimeError with the retcode."""

    def fake_ydl_factory(opts: dict) -> _FakeYoutubeDL:
        return _FakeYoutubeDL(opts, retcode=1, write_file=True)

    with (
        patch("yt_dlp.YoutubeDL", fake_ydl_factory),
        patch.object(audio, "extract_audio"),
    ):
        with pytest.raises(RuntimeError, match="retcode=1"):
            audio.download_audio_via_ytdlp(
                "https://www.youtube.com/watch?v=abcdefghijk",
                str(tmp_path),
                info={"id": "abcdefghijk", "title": "test"},
            )


def test_real_youtubedl_exposes_download_retcode() -> None:
    """Guard against yt-dlp API drift of the private _download_retcode attribute."""
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        assert hasattr(ydl, "_download_retcode")
