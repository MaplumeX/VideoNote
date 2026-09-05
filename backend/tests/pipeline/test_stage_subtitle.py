"""Tests for SubtitleStage: SRT/VTT parsing fixtures, language priority, miss semantics."""

from __future__ import annotations

import pytest

import app.pipeline.subprocess_util as subprocess_util
from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages.base import ProviderConfig, StageContext
from app.pipeline.stages.subtitle import (
    SubtitleStage,
    parse_srt_or_vtt,
    subtitle_languages,
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


def make_ctx(store: FakeStore | None = None, language: str = "en") -> StageContext:
    return StageContext(
        job_id="job-1",
        language=language,
        provider=ProviderConfig(),
        artifacts=store or FakeStore(),
        progress=Recorder(),
        register_cancel=NoopRegistrar(),
        extra={"url": "https://youtu.be/x"},
    )


def write_stub_ytdlp(tmp_path, script: str) -> str:  # type: ignore[no-untyped-def]
    stub = tmp_path / "yt-dlp"
    stub.write_text(script)
    stub.chmod(0o755)
    return str(stub)


class TestParseSrtOrVtt:
    def test_srt_produces_timestamp_links(self) -> None:
        raw = (
            "1\n"
            "00:00:01,000 --> 00:00:03,000\n"
            "Hello world\n"
            "\n"
            "2\n"
            "00:00:05,500 --> 00:00:07,000\n"
            "Second line\n"
        )
        assert parse_srt_or_vtt(raw) == (
            "[00:00:01](#t=1) Hello world\n[00:00:05](#t=5) Second line"
        )

    def test_vtt_produces_timestamp_links(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:03.000\n"
            "Hello from VTT\n"
        )
        assert parse_srt_or_vtt(raw) == "[00:00:01](#t=1) Hello from VTT"

    def test_vtt_note_block_skipped(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "NOTE just a note\n\n"
            "00:00:02.000 --> 00:00:04.000\n"
            "Actual cue\n"
        )
        assert parse_srt_or_vtt(raw) == "[00:00:02](#t=2) Actual cue"

    def test_multiline_cue_joined_with_space(self) -> None:
        raw = "1\n00:00:01,000 --> 00:00:03,000\nline one\nline two\n"
        assert parse_srt_or_vtt(raw) == "[00:00:01](#t=1) line one line two"

    def test_empty_text_cue_dropped(self) -> None:
        raw = "1\n00:00:01,000 --> 00:00:03,000\n\n2\n00:00:05,000 --> 00:00:06,000\nreal\n"
        assert parse_srt_or_vtt(raw) == "[00:00:05](#t=5) real"

    def test_no_cue_returns_none(self) -> None:
        assert parse_srt_or_vtt("") is None
        assert parse_srt_or_vtt("not a subtitle") is None
        assert parse_srt_or_vtt("WEBVTT\n\nNOTE just a note") is None


class TestSubtitleLanguages:
    def test_zh_priority(self) -> None:
        assert subtitle_languages("zh-CN") == ["zh-Hans", "zh", "en", "ja"]
        assert subtitle_languages("zh-TW") == ["zh-Hans", "zh", "en", "ja"]

    def test_non_zh_priority(self) -> None:
        assert subtitle_languages("en") == ["en", "zh-Hans", "zh", "ja"]
        assert subtitle_languages("ja") == ["en", "zh-Hans", "zh", "ja"]


class TestSubtitleStage:
    @pytest.fixture(autouse=True)
    def _restore_bin(self) -> None:
        yield
        subprocess_util.YT_DLP_BIN = "yt-dlp"

    def _stub_with_subtitle(self, tmp_path, filename: str, content: str) -> str:  # type: ignore[no-untyped-def]
        # yt-dlp stub: record argv and "download" a subtitle file into the -o dir.
        # Content is written as a base64 blob to avoid shell quoting pitfalls.
        import base64

        blob = base64.b64encode(content.encode()).decode()
        script = f'''#!/bin/sh
ARGV_FILE="{tmp_path}/argv.txt"
for a in "$@"; do echo "$a" >> "$ARGV_FILE"; done
OUT=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then OUT="$a"; fi
  prev="$a"
done
DIR=$(dirname "$OUT")
echo {blob} | base64 -d > "$DIR/{filename}"
exit 0
'''
        return write_stub_ytdlp(tmp_path, script)

    async def test_hit_writes_subtitle_artifact(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = self._stub_with_subtitle(
            tmp_path, "video.en.srt", "1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        )
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)

        ctx = make_ctx(language="en")
        result = await SubtitleStage().run(ctx, resume=False)
        assert ArtifactKind.subtitle in result.outputs
        assert result.outputs[ArtifactKind.subtitle] == "[00:00:01](#t=1) Hello"
        # argv assertions
        recorded = (tmp_path / "argv.txt").read_text().splitlines()
        assert "--write-subs" in recorded
        assert "--write-auto-subs" in recorded
        assert "--skip-download" in recorded
        assert "--sub-format" in recorded and "srt" in recorded
        assert "--convert-subs" in recorded
        sublangs_idx = recorded.index("--sub-langs")
        assert recorded[sublangs_idx + 1] == "en,zh-Hans,zh,ja"

    async def test_miss_returns_empty_outputs(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stub that succeeds but writes no subtitle file.
        stub = write_stub_ytdlp(tmp_path, "#!/bin/sh\nexit 0\n")
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)

        result = await SubtitleStage().run(make_ctx(), resume=False)
        assert result.outputs == {}

    async def test_download_failure_raises_subtitle_extraction_failed(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = write_stub_ytdlp(tmp_path, "#!/bin/sh\necho 'download error' >&2\nexit 1\n")
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)

        with pytest.raises(PipelineError) as exc_info:
            await SubtitleStage().run(make_ctx(), resume=False)
        assert exc_info.value.code is ErrorCode.SUBTITLE_EXTRACTION_FAILED

    async def test_language_priority_prefers_requested_language(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Two subtitle files: zh should win for zh-CN note language.
        import base64

        en_blob = base64.b64encode(
            b"1\n00:00:01,000 --> 00:00:02,000\nEnglish cue\n"
        ).decode()
        zh_blob = base64.b64encode(
            b"1\n00:00:01,000 --> 00:00:02,000\nChinese cue\n"
        ).decode()
        script = f'''#!/bin/sh
OUT=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then OUT="$a"; fi
  prev="$a"
done
DIR=$(dirname "$OUT")
echo {en_blob} | base64 -d > "$DIR/video.en.srt"
echo {zh_blob} | base64 -d > "$DIR/video.zh-Hans.srt"
exit 0
'''
        stub = write_stub_ytdlp(tmp_path, script)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)

        ctx = make_ctx(language="zh-CN")
        result = await SubtitleStage().run(ctx, resume=False)
        assert "Chinese cue" in str(result.outputs[ArtifactKind.subtitle])

    async def test_resume_skips_when_artifact_present(self) -> None:
        store = FakeStore()
        store.items[ArtifactKind.subtitle] = "[00:00:01](#t=1) cached"
        ctx = make_ctx(store=store)
        result = await SubtitleStage().run(ctx, resume=True)
        assert result.outputs[ArtifactKind.subtitle] == "[00:00:01](#t=1) cached"

    async def test_missing_url_raises(self) -> None:
        ctx = StageContext(
            job_id="j",
            language="en",
            provider=ProviderConfig(),
            artifacts=FakeStore(),
            progress=Recorder(),
            register_cancel=NoopRegistrar(),
        )
        with pytest.raises(PipelineError) as exc_info:
            await SubtitleStage().run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.PROCESSING_FAILED
