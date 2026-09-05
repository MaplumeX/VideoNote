"""Tests for TranscribeStage: fake ASR client — single/multi chunk, SiliconFlow, cancel, errors."""

from __future__ import annotations

import asyncio
import math
import struct
import wave
from typing import ClassVar

import pytest

from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages.base import ProviderConfig, ProviderEndpoint, StageContext
from app.pipeline.stages.transcribe import (
    TranscribeStage,
    asr_language,
    format_timestamp,
    shift_timestamps,
)
from app.pipeline.state import ArtifactKind


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


class FakeASRClient:
    """Scripted fake TranscriptionClient: pops canned responses per call."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    async def transcribe(
        self,
        *,
        model: str,
        file_path: str,
        language: str | None,
        provider: str,
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "file_path": file_path,
                "language": language,
                "provider": provider,
            }
        )
        if not self.responses:
            raise AssertionError("FakeASRClient: no scripted response left")
        resp = self.responses.pop(0)
        if isinstance(resp, BaseException):
            raise resp
        await asyncio.sleep(0)  # await point where cancellation can land
        return resp


class StubStage(TranscribeStage):
    """TranscribeStage with an injected fake client."""

    def __init__(self, fake: FakeASRClient) -> None:
        self.fake = fake

    def _build_client(self, endpoint: ProviderEndpoint) -> FakeASRClient:
        return self.fake


def make_ctx(
    audio_path: str,
    *,
    provider: str = "openai",
    language: str = "en",
    store: FakeStore | None = None,
) -> StageContext:
    endpoint = ProviderEndpoint(
        api_key="k", api_base="https://asr.example/v1", model="whisper-1", provider=provider
    )
    return StageContext(
        job_id="job-1",
        language=language,
        provider=ProviderConfig(asr=endpoint),
        artifacts=store or FakeStore(),
        progress=Recorder(),
        register_cancel=NoopRegistrar(),
        extra={"audio_path": audio_path},
    )


def make_sine_wav(path: str, seconds: float = 0.5, rate: int = 16000) -> str:
    n = int(rate * seconds)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        for i in range(n):
            w.writeframes(struct.pack("<h", int(20000 * math.sin(2 * math.pi * 440 * i / rate))))
    return path


class TestAsrLanguage:
    def test_mapping(self) -> None:
        assert asr_language("zh-CN") == "zh"
        assert asr_language("en") == "en"
        assert asr_language("ja") == "ja"
        assert asr_language("fr") is None
        assert asr_language("zh-TW") is None


class TestShiftTimestamps:
    def test_adds_offset(self) -> None:
        text = "[00:00:01](#t=1) hello\n[00:01:02](#t=62) world"
        out = shift_timestamps(text, 60.0)
        assert out == "[00:01:01](#t=61) hello\n[00:02:02](#t=122) world"

    def test_zero_offset_passthrough(self) -> None:
        text = "[00:00:01](#t=1) hello"
        assert shift_timestamps(text, 0) == text

    def test_plain_text_unchanged(self) -> None:
        assert shift_timestamps("plain line", 100.0) == "plain line"


class TestFormatTimestamp:
    def test_format(self) -> None:
        assert format_timestamp(0) == "00:00:00"
        assert format_timestamp(3661.9) == "01:01:01"


class TestTranscribeStage:
    phase: ClassVar[str] = "transcribe"

    async def test_single_chunk_transcription(self, tmp_path) -> None:
        audio = make_sine_wav(str(tmp_path / "a.wav"))
        fake = FakeASRClient(["[00:00:00](#t=0) hello world"])
        ctx = make_ctx(audio)
        result = await StubStage(fake).run(ctx, resume=False)

        assert result.outputs[ArtifactKind.transcript] == "[00:00:00](#t=0) hello world"
        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["model"] == "whisper-1"
        assert call["language"] == "en"
        assert call["provider"] == "openai"
        # progress: 0.0 -> 1.0
        assert ctx.progress.events[0] == ("transcribe", 0.0, "Transcribing audio")
        assert ctx.progress.events[-1] == ("transcribe", 1.0, "Transcription complete")

    async def test_language_none_for_unmapped(self, tmp_path) -> None:
        audio = make_sine_wav(str(tmp_path / "a.wav"))
        fake = FakeASRClient(["text"])
        ctx = make_ctx(audio, language="fr")
        await StubStage(fake).run(ctx, resume=False)
        assert fake.calls[0]["language"] is None

    async def test_zh_language_mapping(self, tmp_path) -> None:
        audio = make_sine_wav(str(tmp_path / "a.wav"))
        fake = FakeASRClient(["text"])
        ctx = make_ctx(audio, language="zh-CN")
        await StubStage(fake).run(ctx, resume=False)
        assert fake.calls[0]["language"] == "zh"

    async def test_siliconflow_uses_plain_text(self, tmp_path) -> None:
        audio = make_sine_wav(str(tmp_path / "a.wav"))
        fake = FakeASRClient(["plain siliconflow text"])
        ctx = make_ctx(audio, provider="siliconflow")
        result = await StubStage(fake).run(ctx, resume=False)
        assert result.outputs[ArtifactKind.transcript] == "plain siliconflow text"
        assert fake.calls[0]["provider"] == "siliconflow"

    async def test_provider_not_configured_raises(self, tmp_path) -> None:
        audio = make_sine_wav(str(tmp_path / "a.wav"))
        ctx = StageContext(
            job_id="j",
            language="en",
            provider=ProviderConfig(),  # empty endpoint
            artifacts=FakeStore(),
            progress=Recorder(),
            register_cancel=NoopRegistrar(),
            extra={"audio_path": audio},
        )
        with pytest.raises(PipelineError) as exc_info:
            await TranscribeStage().run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.PROVIDER_NOT_CONFIGURED

    async def test_missing_audio_path_raises(self) -> None:
        ctx = StageContext(
            job_id="j",
            language="en",
            provider=ProviderConfig(
                asr=ProviderEndpoint(api_key="k", api_base="b", model="m")
            ),
            artifacts=FakeStore(),
            progress=Recorder(),
            register_cancel=NoopRegistrar(),
        )
        with pytest.raises(PipelineError) as exc_info:
            await TranscribeStage().run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.PROCESSING_FAILED

    async def test_asr_error_wrapped_as_transcription_failed(self, tmp_path) -> None:
        audio = make_sine_wav(str(tmp_path / "a.wav"))
        fake = FakeASRClient([RuntimeError("asr exploded")])
        ctx = make_ctx(audio)
        with pytest.raises(PipelineError) as exc_info:
            await StubStage(fake).run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.TRANSCRIPTION_FAILED
        assert exc_info.value.__cause__ is not None

    async def test_resume_skips_when_artifact_present(self, tmp_path) -> None:
        audio = make_sine_wav(str(tmp_path / "a.wav"))
        fake = FakeASRClient(["should-not-be-called"])
        store = FakeStore()
        store.items[ArtifactKind.transcript] = "cached transcript"
        ctx = make_ctx(audio, store=store)
        result = await StubStage(fake).run(ctx, resume=True)
        assert result.outputs[ArtifactKind.transcript] == "cached transcript"
        assert fake.calls == []

    async def test_cancellation_propagates_and_no_further_calls(self, tmp_path) -> None:
        audio = make_sine_wav(str(tmp_path / "a.wav"))

        class CancellingClient(FakeASRClient):
            async def transcribe(self, **kwargs):  # type: ignore[override]
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    raise asyncio.CancelledError()
                return "should not happen"

        fake = CancellingClient(["a", "b"])
        ctx = make_ctx(audio)
        with pytest.raises(asyncio.CancelledError):
            await StubStage(fake).run(ctx, resume=False)
        # No follow-up call was started after cancellation.
        assert len(fake.calls) == 1


class TestTranscribeStageLargeFile:
    """Multi-chunk path: force the split by shrinking the size limit."""

    @pytest.fixture(autouse=True)
    def _small_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.pipeline.stages.transcribe as mod

        monkeypatch.setattr(mod, "MAX_FILE_SIZE_BYTES_OPENAI", 1)  # always split

    async def test_multi_chunk_offset_stitching(self, tmp_path) -> None:
        audio = make_sine_wav(str(tmp_path / "a.wav"), seconds=1.0, rate=16000)
        fake = FakeASRClient(["[00:00:01](#t=1) chunk one"])
        ctx = make_ctx(audio)
        result = await StubStage(fake).run(ctx, resume=False)
        # 1s audio with min chunk 30s => exactly 1 chunk, offset 0
        assert result.outputs[ArtifactKind.transcript] == "[00:00:01](#t=1) chunk one"
        assert len(fake.calls) == 1

    async def test_two_chunks_offsets_applied(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Shrink the min chunk duration to 1s so a 2.5s file makes 3 chunks,
        # exercising the real splitting loop + timestamp offset stitching.
        import app.pipeline.stages.transcribe as mod

        monkeypatch.setattr(mod, "MAX_FILE_SIZE_BYTES_OPENAI", 1)
        monkeypatch.setattr(mod, "MIN_CHUNK_DURATION_SECONDS", 1.0)

        audio = make_sine_wav(str(tmp_path / "a.wav"), seconds=2.5, rate=16000)
        fake = FakeASRClient(
            [
                "[00:00:00](#t=0) first",
                "[00:00:00](#t=0) second",
                "[00:00:00](#t=0) third",
            ]
        )
        ctx = make_ctx(audio)
        result = await StubStage(fake).run(ctx, resume=False)

        lines = str(result.outputs[ArtifactKind.transcript]).splitlines()
        assert len(lines) == 3
        # Offsets: 0.0, 1.0, 2.0 (1s chunks)
        assert lines[0] == "[00:00:00](#t=0) first"
        assert lines[1] == "[00:00:01](#t=1) second"
        assert lines[2] == "[00:00:02](#t=2) third"
        # chunk files actually created (ffmpeg ran)
        assert len(fake.calls) == 3
        # per-chunk progress published
        messages = [e[2] for e in ctx.progress.events]
        assert "Transcribing chunk 1..." in messages
        assert "Transcribing chunk 3..." in messages
