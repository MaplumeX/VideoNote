"""Tests for AudioStage: real ffmpeg with a 1s sine-wave fixture, stub yt-dlp for URL."""

from __future__ import annotations

import asyncio
import wave

import pytest

import app.pipeline.stages.audio as audio_stage
import app.pipeline.subprocess_util as subprocess_util
from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages.audio import AudioStage, extract_audio_wav
from app.pipeline.stages.base import ProviderConfig, StageContext


class FakeStore:
    def __init__(self) -> None:
        self.items: dict = {}

    async def get(self, kind) -> object | None:
        return self.items.get(kind)

    async def put(self, kind, content) -> None:
        self.items[kind] = content


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, float, str]] = []

    async def publish(self, phase, fraction: float, message: str) -> None:
        self.events.append((phase.value, fraction, message))


class NoopRegistrar:
    def __call__(self, handle) -> None:  # type: ignore[no-untyped-def]
        pass


def make_ctx(**extra: object) -> StageContext:
    return StageContext(
        job_id="job-1",
        language="en",
        provider=ProviderConfig(),
        artifacts=FakeStore(),
        progress=Recorder(),
        register_cancel=NoopRegistrar(),
        extra=extra,
    )


def make_sine_wav(path: str, seconds: float = 1.0, rate: int = 44100) -> str:
    """Generate a 1s mono sine-wave WAV fixture (440 Hz)."""
    import math
    import struct

    n = int(rate * seconds)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        for i in range(n):
            value = int(20000 * math.sin(2 * math.pi * 440 * i / rate))
            w.writeframes(struct.pack("<h", value))
    return path


class TestExtractAudioWav:
    async def test_converts_to_16khz_mono_pcm(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = make_sine_wav(str(tmp_path / "input.wav"))
        out = str(tmp_path / "out.wav")
        await extract_audio_wav(src, out, register_cancel=NoopRegistrar())

        with wave.open(out, "rb") as w:
            assert w.getframerate() == 16000
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2  # pcm_s16le
            assert w.getnframes() > 0

    async def test_failure_raises_audio_extraction_failed(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Not a media file: ffmpeg exits nonzero.
        bad = tmp_path / "bad.bin"
        bad.write_bytes(b"not media")
        with pytest.raises(PipelineError) as exc_info:
            await extract_audio_wav(
                str(bad), str(tmp_path / "out.wav"), register_cancel=NoopRegistrar()
            )
        assert exc_info.value.code is ErrorCode.AUDIO_EXTRACTION_FAILED


class TestAudioStageFileSource:
    async def test_upload_source_extracts_and_exposes_audio_path(
        self, tmp_path
    ) -> None:
        src = make_sine_wav(str(tmp_path / "upload.mp4.wav"))
        ctx = make_ctx(input_path=src)
        result = await AudioStage().run(ctx, resume=False)

        audio_path = result.extra["audio_path"]
        assert isinstance(audio_path, str)
        with wave.open(audio_path, "rb") as w:
            assert w.getframerate() == 16000
            assert w.getnchannels() == 1
        # progress sequence
        phases = [e[0] for e in ctx.progress.events]
        assert phases == ["audio", "audio"]
        assert ctx.progress.events[0][1] == 0.0
        assert ctx.progress.events[-1][1] == 1.0

    async def test_upload_failure_never_uses_video_fetch_failed(self, tmp_path) -> None:
        bad = tmp_path / "bad.bin"
        bad.write_bytes(b"junk")
        ctx = make_ctx(input_path=str(bad))
        with pytest.raises(PipelineError) as exc_info:
            await AudioStage().run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.AUDIO_EXTRACTION_FAILED


class TestAudioStageUrlSource:
    @pytest.fixture(autouse=True)
    def _restore_bin(self) -> None:
        yield
        subprocess_util.YT_DLP_BIN = "yt-dlp"

    async def test_url_download_and_convert(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # yt-dlp stub: records argv, "downloads" a valid wav named audio.webm
        import base64

        # Build a small valid wav in python, base64 it into the stub.
        import io

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            import math
            import struct

            for i in range(44100):
                w.writeframes(
                    struct.pack("<h", int(20000 * math.sin(2 * math.pi * 440 * i / 44100)))
                )
        blob = base64.b64encode(buf.getvalue()).decode()

        argv_path = tmp_path / "argv.txt"
        stub = tmp_path / "yt-dlp"
        stub.write_text(
            "#!/bin/sh\n"
            f"for a in \"$@\"; do echo \"$a\" >> {argv_path}; done\n"
            "OUT=\"\"\nprev=\"\"\n"
            "for a in \"$@\"; do\n"
            "  if [ \"$prev\" = \"-o\" ]; then OUT=\"$a\"; fi\n"
            "  prev=\"$a\"\n"
            "done\n"
            f"echo {blob} | base64 -d > \"$OUT.webm\"\n"
            "exit 0\n"
        )
        stub.chmod(0o755)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", str(stub))

        ctx = make_ctx(url="https://youtu.be/x")
        result = await AudioStage().run(ctx, resume=False)
        audio_path = result.extra["audio_path"]
        with wave.open(audio_path, "rb") as w:
            assert w.getframerate() == 16000
            assert w.getnchannels() == 1

        recorded = argv_path.read_text().splitlines()
        fmt_idx = recorded.index("-f")
        assert recorded[fmt_idx + 1] == "bestaudio/best"

    async def test_cookiefile_passed_to_ytdlp_url_download(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ctx.extra['cookiefile'] must reach the yt-dlp argv (--cookies) —
        URL branch only (uploads never invoke yt-dlp)."""
        # Stub: records argv, fails the download (assertion is on argv).
        argv_path = tmp_path / "argv.txt"
        stub = tmp_path / "yt-dlp"
        stub.write_text(
            "#!/bin/sh\n"
            f"for a in \"$@\"; do echo \"$a\" >> {argv_path}; done\n"
            "echo 'download failed' >&2\nexit 1\n"
        )
        stub.chmod(0o755)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", str(stub))

        cookiefile = str(tmp_path / "cookies.txt")
        ctx = make_ctx(url="https://youtu.be/x", cookiefile=cookiefile)
        with pytest.raises(PipelineError):
            await AudioStage().run(ctx, resume=False)
        recorded = argv_path.read_text().splitlines()
        cookies_idx = recorded.index("--cookies")
        assert recorded[cookies_idx + 1] == cookiefile

    async def test_no_cookiefile_key_falls_back_to_shared_opts(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without a cookiefile in extra, argv carries no --cookies from the stage."""
        argv_path = tmp_path / "argv.txt"
        stub = tmp_path / "yt-dlp"
        stub.write_text(
            "#!/bin/sh\n"
            f"for a in \"$@\"; do echo \"$a\" >> {argv_path}; done\n"
            "echo 'download failed' >&2\nexit 1\n"
        )
        stub.chmod(0o755)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", str(stub))

        ctx = make_ctx(url="https://youtu.be/x")
        with pytest.raises(PipelineError):
            await AudioStage().run(ctx, resume=False)
        recorded = argv_path.read_text().splitlines()
        assert "--cookies" not in recorded

    async def test_url_download_failure_raises_video_fetch_failed(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = tmp_path / "yt-dlp"
        stub.write_text("#!/bin/sh\necho 'download failed' >&2\nexit 1\n")
        stub.chmod(0o755)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", str(stub))

        ctx = make_ctx(url="https://youtu.be/x")
        with pytest.raises(PipelineError) as exc_info:
            await AudioStage().run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_FETCH_FAILED
        # detail carries the real stderr line, not just the retcode
        assert "download failed" in exc_info.value.detail

    async def test_transient_failure_retried_and_succeeds(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transport-class failure on attempt 1, success on attempt 2 ->
        the stage retries (with backoff) instead of failing the task."""
        import base64
        import io

        monkeypatch.setattr(audio_stage, "_RETRY_DELAY_SECONDS", 0.01)

        # A valid 1s wav payload for the successful attempt.
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            import math
            import struct

            for i in range(44100):
                w.writeframes(
                    struct.pack("<h", int(20000 * math.sin(2 * math.pi * 440 * i / 44100)))
                )
        blob = base64.b64encode(buf.getvalue()).decode()

        argv_path = tmp_path / "argv.txt"
        calls_path = tmp_path / "calls.txt"
        stub = tmp_path / "yt-dlp"
        stub.write_text(
            "#!/bin/sh\n"
            "echo x >> " + str(calls_path) + "\n"
            "if [ $(cat " + str(calls_path) + " | wc -l) -eq 1 ]; then\n"
            "  echo 'ERROR: [download] Remote end closed connection' >&2\n"
            "  exit 1\n"
            "fi\n"
            "OUT=\"\"\nprev=\"\"\n"
            "for a in \"$@\"; do\n"
            "  echo \"$a\" >> " + str(argv_path) + "\n"
            "  if [ \"$prev\" = \"-o\" ]; then OUT=\"$a\"; fi\n"
            "  prev=\"$a\"\n"
            "done\n"
            "echo " + blob + " | base64 -d > \"$OUT.webm\"\n"
            "exit 0\n"
        )
        stub.chmod(0o755)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", str(stub))

        ctx = make_ctx(url="https://bilibili.com/video/BV1")
        result = await AudioStage().run(ctx, resume=False)
        assert calls_path.read_text().splitlines() == ["x", "x"]
        with wave.open(result.extra["audio_path"], "rb") as w:
            assert w.getframerate() == 16000
            assert w.getnchannels() == 1

    async def test_deterministic_error_fails_fast_no_retry(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A classified deterministic error (private video) must raise on the
        first attempt without consuming retries."""
        monkeypatch.setattr(audio_stage, "_RETRY_DELAY_SECONDS", 0.01)
        calls_path = tmp_path / "calls.txt"
        stub = tmp_path / "yt-dlp"
        stub.write_text(
            "#!/bin/sh\n"
            "echo x >> " + str(calls_path) + "\n"
            "echo 'ERROR: This video is private' >&2\n"
            "exit 1\n"
        )
        stub.chmod(0o755)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", str(stub))

        ctx = make_ctx(url="https://youtu.be/x")
        with pytest.raises(PipelineError) as exc_info:
            await AudioStage().run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_PRIVATE
        assert calls_path.read_text().splitlines() == ["x"]  # exactly one call

    async def test_all_attempts_exhausted_raises_with_real_detail(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(audio_stage, "_RETRY_DELAY_SECONDS", 0.01)
        calls_path = tmp_path / "calls.txt"
        stub = tmp_path / "yt-dlp"
        stub.write_text(
            "#!/bin/sh\n"
            "echo x >> " + str(calls_path) + "\n"
            "echo 'ERROR: Remote end closed connection. Giving up after 10 retries' >&2\n"
            "exit 1\n"
        )
        stub.chmod(0o755)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", str(stub))

        ctx = make_ctx(url="https://bilibili.com/video/BV1")
        with pytest.raises(PipelineError) as exc_info:
            await AudioStage().run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_FETCH_FAILED
        # the real stderr diagnosis survives into the detail
        assert "Remote end closed" in exc_info.value.detail
        assert calls_path.read_text().splitlines() == ["x", "x", "x"]  # 3 attempts

    async def test_detail_sanitizes_cookie_secret(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(audio_stage, "_RETRY_DELAY_SECONDS", 0.01)
        stub = tmp_path / "yt-dlp"
        stub.write_text(
            "#!/bin/sh\n"
            "echo 'ERROR: Cookie: secret-token failed; request rejected' >&2\n"
            "exit 1\n"
        )
        stub.chmod(0o755)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", str(stub))

        ctx = make_ctx(url="https://youtu.be/x")
        with pytest.raises(PipelineError) as exc_info:
            await AudioStage().run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_COOKIE_INVALID
        assert "secret-token" not in exc_info.value.detail

    async def test_cancel_during_retry_sleep_propagates(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cancellation arriving while the retry backoff sleeps must propagate
        as CancelledError and stop further attempts."""
        monkeypatch.setattr(audio_stage, "_RETRY_DELAY_SECONDS", 5.0)
        calls_path = tmp_path / "calls.txt"
        stub = tmp_path / "yt-dlp"
        stub.write_text(
            "#!/bin/sh\n"
            "echo x >> " + str(calls_path) + "\n"
            "echo 'Remote end closed connection' >&2\n"
            "exit 1\n"
        )
        stub.chmod(0o755)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", str(stub))

        ctx = make_ctx(url="https://youtu.be/x")
        task = asyncio.create_task(AudioStage().run(ctx, resume=False))
        # Wait for the first (failing) attempt to finish, then cancel while
        # the retry backoff is sleeping.
        while not calls_path.exists():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Exactly one yt-dlp attempt ran — the retry never started.
        assert calls_path.read_text().splitlines() == ["x"]

    async def test_no_source_raises_processing_failed(self) -> None:
        with pytest.raises(PipelineError) as exc_info:
            await AudioStage().run(make_ctx(), resume=False)
        assert exc_info.value.code is ErrorCode.PROCESSING_FAILED
