"""Shared pytest fixtures for pipeline tests (C4).

Provides an isolated on-disk SQLite database (the real schema via
``app.db.init_db``) with ``UPLOAD_DIR``/``DB_PATH`` monkeypatched per test, a
pair of authenticated TestClient helpers, and a fake-stage orchestrator setup
used by the orchestrator/routes/recovery integration tests.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth import TokenData, get_current_user
from app.main import app
from app.pipeline.context import ExecutionPlan
from app.pipeline.orchestrator import Orchestrator
from app.pipeline.stages.base import (
    ArtifactStore,
    ProviderConfig,
    ProviderEndpoint,
    StageContext,
    StageResult,
)
from app.pipeline.state import ArtifactKind, PipelinePhase

# --- Database isolation ------------------------------------------------------

@pytest.fixture
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the DB + upload dir at a temp dir and initialize the real schema."""
    upload_dir = tmp_path / "uploads"
    database_path = upload_dir / "videonote.db"
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    import app.config as config
    monkeypatch.setattr(config, "UPLOAD_DIR", upload_dir)
    await db.init_db()
    yield upload_dir
    await db.close_db()

# --- Auth / TestClient ------------------------------------------------------

TEST_USER = TokenData(user_id="user-1")


@pytest.fixture
def current_user(monkeypatch: pytest.MonkeyPatch) -> TokenData:
    """Bypass JWT auth for every request (dependency override)."""
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    yield TEST_USER
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def other_user(monkeypatch: pytest.MonkeyPatch) -> TokenData:
    """Bypass JWT auth as a different user (permission tests)."""
    other = TokenData(user_id="user-2")
    app.dependency_overrides[get_current_user] = lambda: other
    yield other
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client(current_user: TokenData) -> TestClient:
    """TestClient with auth bypassed (no lifespan — init DB via isolated_db)."""
    return TestClient(app)

# --- Raw-ASGI SSE consumption -------------------------------------------------

async def consume_sse_events(
    asgi_app,
    path: str,
    *,
    max_events: int = 10,
    timeout: float = 10.0,
) -> tuple[int, list[tuple[str, str]]]:
    """Consume an SSE endpoint via a raw ASGI call; returns (status, events).

    ``TestClient`` / ``httpx.ASGITransport`` both await the *entire* response
    body before returning a response, which deadlocks forever on an SSE
    stream that only ends at a terminal state (up to 30 minutes). Instead we
    drive the ASGI app directly: body chunks are parsed as they arrive, and
    once ``max_events`` events have been seen the client side answers any
    pending ``receive()`` with ``http.disconnect`` so ``EventSourceResponse``
    stops its stream and the app coroutine returns normally.

    Auth is expected to be bypassed via ``app.dependency_overrides`` (the
    ``current_user``/``other_user`` fixtures) — no Authorization header is
    sent, the raw scope carries none.
    """
    events: list[tuple[str, str]] = []
    state = {"status": 0, "disconnect": False}
    buffer_holder = [b""]

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"accept", b"text/event-stream"),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> dict:
        # sse-starlette listens for a disconnect while streaming; block until
        # the consumer decides to disconnect (or the app returns on its own,
        # dropping this coroutine).
        deadline = time.monotonic() + timeout
        while not state["disconnect"]:
            if time.monotonic() > deadline:
                return {"type": "http.disconnect"}
            await asyncio.sleep(0.01)
        return {"type": "http.disconnect"}

    def _drain_buffer() -> None:
        while True:
            buffer = buffer_holder[0]
            sep = -1
            sep_len = 0
            for cand, ln in ((b"\r\n\r\n", 4), (b"\n\n", 2)):
                idx = buffer.find(cand)
                if idx != -1 and (sep == -1 or idx < sep):
                    sep, sep_len = idx, ln
            if sep == -1:
                return
            block, buffer = buffer[:sep], buffer[sep + sep_len :]
            buffer_holder[0] = buffer
            event_name, data = "message", ""
            for line in block.decode("utf-8", errors="replace").splitlines():
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
            events.append((event_name, data))
            if len(events) >= max_events:
                state["disconnect"] = True

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            state["status"] = message["status"]
        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            if body:
                buffer_holder[0] += body
                _drain_buffer()

    async def _run() -> None:
        await asgi_app(scope, receive, send)

    await asyncio.wait_for(_run(), timeout=timeout)
    return state["status"], events

# --- Fake stages -------------------------------------------------------------


class FakeStore(ArtifactStore):
    """In-memory artifact store (never touches SQLite)."""

    def __init__(self) -> None:
        self.data: dict[ArtifactKind, object] = {}

    async def get(self, kind: ArtifactKind) -> object | None:
        return self.data.get(kind)

    async def put(self, kind: ArtifactKind, content: object) -> None:
        self.data[kind] = content


class FakePublisher:
    """Records progress publications for assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[PipelinePhase, float, str]] = []

    async def publish(self, phase: PipelinePhase, fraction: float, message: str) -> None:
        self.events.append((phase, fraction, message))


def fake_stage(
    phase: PipelinePhase,
    *,
    outputs: dict[ArtifactKind, object] | None = None,
    extra: dict[str, object] | None = None,
    delay: float = 0.0,
    error: Exception | None = None,
    on_run=None,
):
    """Build a minimal fake stage; records calls in ``calls``/``resumes``."""

    phase_ = phase
    outputs_ = outputs
    extra_ = extra
    delay_ = delay
    error_ = error
    on_run_ = on_run

    class _FakeStage:
        phase: ClassVar[PipelinePhase] = phase_
        calls: list[StageContext] = []
        resumes: list[bool] = []

        async def run(self, ctx: StageContext, *, resume: bool) -> StageResult:
            _FakeStage.calls.append(ctx)
            _FakeStage.resumes.append(resume)
            if on_run_ is not None:
                on_run_(ctx, resume)
            if delay_:
                await asyncio.sleep(delay_)
            if error_ is not None:
                raise error_
            return StageResult(
                outputs=dict(outputs_ or {}), extra=dict(extra_ or {})
            )

    return _FakeStage()


def recording_registry() -> Orchestrator:
    """An Orchestrator with real stages stripped (tests inject fakes)."""
    o = Orchestrator()
    o.stages = {}
    return o


def make_plan(
    job_id: str,
    *,
    source_type: str = "url",
    url: str | None = "https://www.youtube.com/watch?v=x",
    input_path: str | None = None,
    language: str = "en",
    path: tuple[PipelinePhase, ...] | None = None,
) -> ExecutionPlan:
    """Build a fully-configured ExecutionPlan for tests."""
    from app.pipeline.state import FILE_PATH, URL_PATH

    if path is None:
        path = URL_PATH if source_type != "upload" else FILE_PATH
    return ExecutionPlan(
        job_id=job_id,
        source_type=source_type,
        language=language,
        provider=ProviderConfig(
            asr=ProviderEndpoint(api_key="k", api_base="http://asr", model="m"),
            llm=ProviderEndpoint(api_key="k", api_base="http://llm", model="m"),
        ),
        path=path,
        url=url if source_type != "upload" else None,
        input_path=input_path if source_type == "upload" else None,
    )
