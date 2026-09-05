"""Stage protocol and shared context — the implementation contract for C2/C3.

Every pipeline stage (fetch/subtitle/audio/transcribe/notegen) is a class
with a ``phase`` class attribute and an async ``run`` method taking a
``StageContext``. Inputs/outputs are pure data (artifact kinds); the
orchestrator (C4) owns persistence, scheduling, and cancellation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, Protocol, runtime_checkable

from app.pipeline.progress import ProgressPublisher
from app.pipeline.state import ArtifactKind, PipelinePhase


@dataclass(frozen=True)
class ProviderEndpoint:
    """One external provider endpoint config (ASR or LLM)."""

    api_key: str = ""
    api_base: str = ""
    model: str = ""
    provider: str = ""

    def is_complete(self) -> bool:
        """A provider is usable only when key, base, and model are all set."""
        return bool(self.api_key and self.api_base and self.model)


@dataclass(frozen=True)
class ProviderConfig:
    """Provider configuration carried by StageContext."""

    asr: ProviderEndpoint = field(default_factory=ProviderEndpoint)
    llm: ProviderEndpoint = field(default_factory=ProviderEndpoint)


@runtime_checkable
class ArtifactStore(Protocol):
    """Read/write intermediate artifacts (DB-backed; see app.db)."""

    async def get(self, kind: ArtifactKind) -> object | None: ...

    async def put(self, kind: ArtifactKind, content: object) -> None: ...


# A cancel handle terminates the stage's in-flight work: a subprocess kill or
# an asyncio task cancel, supplied by the stage and invoked by the orchestrator.
CancelHandle = Callable[[], None]

# Registers the current stage's cancel handle. Passing None unregisters it.
CancelHandleRegistrar = Callable[[CancelHandle | None], None]


@dataclass
class StageContext:
    """Everything a stage needs to run, injected by the orchestrator (C4)."""

    job_id: str
    language: str
    provider: ProviderConfig
    artifacts: ArtifactStore
    progress: ProgressPublisher
    register_cancel: CancelHandleRegistrar
    # Task-level inputs that are not artifacts: the source URL (fetch/subtitle/
    # audio URL tasks) and the uploaded file path (audio file tasks), injected
    # by the orchestrator. Keys: "url", "input_path".
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class StageResult:
    """Outputs produced by a stage; the orchestrator persists them.

    ``outputs`` are artifacts keyed by kind; ``extra`` carries values that
    are not artifacts (e.g. C3's ``notes`` text — the orchestrator writes it
    to ``tasks.result_json``; C2's ``audio_path`` for the next stage).
    """

    outputs: dict[ArtifactKind, object] = field(default_factory=dict)
    extra: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Stage(Protocol):
    """A single pipeline phase implementation (target interface for C2/C3)."""

    phase: ClassVar[PipelinePhase]

    async def run(self, ctx: StageContext, *, resume: bool) -> StageResult: ...
