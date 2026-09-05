"""Tests for FetchStage: stub yt-dlp binary, error classification, thumbnail non-fatality."""

from __future__ import annotations

import json
from typing import ClassVar

import httpx
import pytest

import app.pipeline.subprocess_util as subprocess_util
from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages import fetch as fetch_mod
from app.pipeline.stages.base import ProviderConfig, StageContext, StageResult
from app.pipeline.state import ArtifactKind


class FakeStore:
    """In-memory ArtifactStore."""

    def __init__(self) -> None:
        self.items: dict = {}

    async def get(self, kind) -> object | None:
        return self.items.get(kind)

    async def put(self, kind, content) -> None:
        self.items[kind] = content


class Recorder:
    """Progress publisher recording events."""

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


def write_stub_ytdlp(tmp_path, script: str) -> str:  # type: ignore[no-untyped-def]
    stub = tmp_path / "yt-dlp"
    stub.write_text(script)
    stub.chmod(0o755)
    return str(stub)


STUB_OK = """#!/bin/sh
echo '{"title": "My Video", "thumbnail": "https://example.com/thumb.jpg"}'
"""


class TestFetchStage:
    phase: ClassVar[str] = "fetching"

    @pytest.fixture(autouse=True)
    def _restore_bin(self) -> None:
        yield
        subprocess_util.YT_DLP_BIN = "yt-dlp"

    async def test_single_chunk_metadata_and_progress(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = write_stub_ytdlp(
            tmp_path, STUB_OK + "echo '--dump-json --no-download https://youtu.be/x' >> "
            f"{tmp_path}/argv.txt\n"
        )
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)
        # Thumbnail download: stub it non-fatal-free (returns None path)
        monkeypatch.setattr(fetch_mod, "download_thumbnail", self._thumb_ok)

        from app.pipeline.stages.fetch import FetchStage

        ctx = make_ctx(url="https://youtu.be/x")
        result = await FetchStage().run(ctx, resume=False)

        assert isinstance(result, StageResult)
        meta = result.outputs[ArtifactKind.video_meta]
        assert meta.title == "My Video"
        assert meta.thumbnail == "thumb-123.jpg"
        # progress: 0.0 start, 1.0 done
        assert ctx.progress.events[0] == ("fetching", 0.0, "Fetching video info")
        assert ctx.progress.events[-1] == ("fetching", 1.0, "Video info fetched")
        # argv assertions: dump-json + no-download + url + shared opts
        argv_file = tmp_path / "argv.txt"
        assert argv_file.exists()
        recorded = argv_file.read_text().strip().split()
        assert "--dump-json" in recorded
        assert "--no-download" in recorded
        assert "https://youtu.be/x" in recorded

    async def _thumb_ok(self, url: str) -> str | None:
        return "thumb-123.jpg"

    async def test_error_classification_private(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = write_stub_ytdlp(
            tmp_path, "#!/bin/sh\necho 'This video is private' >&2\nexit 1\n"
        )
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)
        from app.pipeline.stages.fetch import FetchStage

        ctx = make_ctx(url="https://youtu.be/x")
        with pytest.raises(PipelineError) as exc_info:
            await FetchStage().run(ctx, resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_PRIVATE

    async def test_error_classification_geo(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = write_stub_ytdlp(
            tmp_path, "#!/bin/sh\necho 'not available in your country' >&2\nexit 1\n"
        )
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)
        from app.pipeline.stages.fetch import FetchStage

        with pytest.raises(PipelineError) as exc_info:
            await FetchStage().run(make_ctx(url="u"), resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_GEO_RESTRICTED

    async def test_error_classification_not_found(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = write_stub_ytdlp(
            tmp_path, "#!/bin/sh\necho 'HTTP Error 404: Not Found' >&2\nexit 1\n"
        )
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)
        from app.pipeline.stages.fetch import FetchStage

        with pytest.raises(PipelineError) as exc_info:
            await FetchStage().run(make_ctx(url="u"), resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_NOT_FOUND

    async def test_error_classification_cookie(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = write_stub_ytdlp(
            tmp_path, "#!/bin/sh\necho 'cookies required to view' >&2\nexit 1\n"
        )
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)
        from app.pipeline.stages.fetch import FetchStage

        with pytest.raises(PipelineError) as exc_info:
            await FetchStage().run(make_ctx(url="u"), resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_COOKIE_INVALID

    async def test_error_classification_fallback(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = write_stub_ytdlp(
            tmp_path, "#!/bin/sh\necho 'some weird failure' >&2\nexit 2\n"
        )
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)
        from app.pipeline.stages.fetch import FetchStage

        with pytest.raises(PipelineError) as exc_info:
            await FetchStage().run(make_ctx(url="u"), resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_FETCH_FAILED

    async def test_thumbnail_failure_is_non_fatal(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = write_stub_ytdlp(tmp_path, STUB_OK)
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)

        async def fail_thumb(url: str) -> str | None:
            raise httpx.ConnectError("boom")

        monkeypatch.setattr(fetch_mod, "download_thumbnail", fail_thumb)
        from app.pipeline.stages.fetch import FetchStage

        result = await FetchStage().run(make_ctx(url="u"), resume=False)
        meta = result.outputs[ArtifactKind.video_meta]
        assert meta.title == "My Video"
        assert meta.thumbnail is None

    async def test_invalid_json_output(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = write_stub_ytdlp(tmp_path, "#!/bin/sh\necho 'not json'\n")
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)
        from app.pipeline.stages.fetch import FetchStage

        with pytest.raises(PipelineError) as exc_info:
            await FetchStage().run(make_ctx(url="u"), resume=False)
        assert exc_info.value.code is ErrorCode.VIDEO_FETCH_FAILED

    async def test_missing_url_raises_processing_failed(self) -> None:
        from app.pipeline.stages.fetch import FetchStage

        with pytest.raises(PipelineError) as exc_info:
            await FetchStage().run(make_ctx(), resume=False)
        assert exc_info.value.code is ErrorCode.PROCESSING_FAILED

    async def test_resume_skips_when_artifact_present(self) -> None:
        from app.pipeline.stages.fetch import FetchStage, VideoMeta

        store = FakeStore()
        store.items[ArtifactKind.video_meta] = VideoMeta("Cached", None)
        ctx = StageContext(
            job_id="j",
            language="en",
            provider=ProviderConfig(),
            artifacts=store,
            progress=Recorder(),
            register_cancel=NoopRegistrar(),
            extra={"url": "u"},
        )
        result = await FetchStage().run(ctx, resume=True)
        assert result.outputs[ArtifactKind.video_meta].title == "Cached"

    async def test_stub_argv_includes_shared_options(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        argv_path = tmp_path / "argv.txt"
        stub = write_stub_ytdlp(
            tmp_path,
            "#!/bin/sh\nfor a in \"$@\"; do echo \"$a\" >> "
            f"{argv_path}\ndone\necho '{json.dumps({'title': 'T'})}'\n",
        )
        monkeypatch.setattr(subprocess_util, "YT_DLP_BIN", stub)
        from app.pipeline.stages.fetch import FetchStage

        await FetchStage().run(make_ctx(url="https://youtu.be/abc"), resume=False)
        recorded = argv_path.read_text().splitlines()
        assert "--quiet" in recorded
        assert "--no-warnings" in recorded
        assert "--remote-components" in recorded
        assert "ejs:github" in recorded
        assert "https://youtu.be/abc" in recorded
