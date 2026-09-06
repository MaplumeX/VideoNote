"""Execution plan, stage registry, and runtime stage-context assembly (C4).

The orchestrator's per-stage wiring lives here: the DB-backed artifact store
adapter, the progress publisher (PhaseProgressTracker + conditional
``update_task_status`` writes), and the cancel-handle registry the
orchestrator's ``cancel()`` triggers.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app import config, db
from app.crypto import decrypt_api_key
from app.pipeline.progress import PhaseProgressTracker
from app.pipeline.stages.audio import AudioStage
from app.pipeline.stages.base import (
    CancelHandle,
    CancelHandleRegistrar,
    ProviderConfig,
    ProviderEndpoint,
    Stage,
    StageContext,
)
from app.pipeline.stages.fetch import FetchStage
from app.pipeline.stages.notegen import NoteGenStage
from app.pipeline.stages.subtitle import SubtitleStage
from app.pipeline.stages.transcribe import TranscribeStage
from app.pipeline.state import (
    FILE_PATH,
    URL_PATH,
    ArtifactKind,
    Checkpoint,
    PipelinePhase,
    next_phases,
)

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {"en", "zh-CN", "ja"}

@dataclass(frozen=True)
class ExecutionPlan:
    """Everything the orchestrator needs to run one task end to end."""

    job_id: str
    source_type: str  # "url" | "upload"
    language: str
    provider: ProviderConfig
    path: tuple[PipelinePhase, ...]
    url: str | None = None
    input_path: str | None = None

def detect_video_platform(url: str) -> str:
    """Detect whether a URL is from YouTube or Bilibili (legacy semantics)."""
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "bilibili.com" in url or "b23.tv" in url:
        return "bilibili"
    return "unknown"

def normalize_language(lang: str | None) -> str:
    """Normalize a language code, falling back to 'en' if unsupported."""
    if lang in SUPPORTED_LANGUAGES:
        return lang  # type: ignore[return-value]
    if lang and lang.startswith("zh"):
        return "zh-CN"
    return "en"

def path_for_source(source_type: str | None) -> tuple[PipelinePhase, ...]:
    """Return the execution path for a task's source type."""
    return URL_PATH if source_type != "upload" else FILE_PATH

# --- STAGES registry ---------------------------------------------------------

STAGES: dict[PipelinePhase, Stage] = {
    PipelinePhase.fetching: FetchStage(),
    PipelinePhase.subtitle: SubtitleStage(),
    PipelinePhase.audio: AudioStage(),
    PipelinePhase.transcribe: TranscribeStage(),
    PipelinePhase.notegen: NoteGenStage(),
}

# --- Checkpoint helpers ------------------------------------------------------

def parse_checkpoint(row: dict | None) -> Checkpoint | None:
    """Build a ``Checkpoint`` from a ``read_checkpoint`` row (None = scratch)."""
    if row is None or row.get("checkpoint_phase") is None:
        return None
    return Checkpoint(
        completed_phase=PipelinePhase(row["checkpoint_phase"]),
    )

def checkpoint_artifacts(plan: ExecutionPlan, checkpoint: Checkpoint | None) -> frozenset:
    """Artifact kinds durably present for the job.

    The persisted ``Checkpoint`` does not carry the artifact set; the kinds are
    derived from the completed phase per the contract's producer table (video_meta
    <- fetching, subtitle <- subtitle, transcript <- transcribe). Additional
    kinds are read from the store lazily by the resume-aware stages themselves.
    """
    if checkpoint is None:
        return frozenset()
    producers: dict[PipelinePhase, ArtifactKind] = {
        PipelinePhase.fetching: ArtifactKind.video_meta,
        PipelinePhase.subtitle: ArtifactKind.subtitle,
        PipelinePhase.transcribe: ArtifactKind.transcript,
    }
    kind = producers.get(checkpoint.completed_phase)
    return frozenset({kind}) if kind is not None else frozenset()

def advance(
    path: tuple[PipelinePhase, ...],
    current: PipelinePhase,
    *,
    artifact_kinds: frozenset,
) -> PipelinePhase | None:
    """Compute the next phase after ``current`` completed within ``path``.

    The subtitle-hit skip is expressed by artifact presence: when the subtitle
    stage produced its artifact, audio+transcribe are bypassed and notegen is
    next (mirroring ``resume_point``'s conditional skip).
    """
    if ArtifactKind.subtitle in artifact_kinds and current is PipelinePhase.subtitle:
        candidates = [
            p for p in next_phases(path, current)
            if p is PipelinePhase.notegen
        ]
        if candidates:
            return candidates[0]
    successors = next_phases(path, current)
    return successors[0] if successors else None

# --- Provider resolution -----------------------------------------------------

async def _user_endpoint(user_id: str | None, category: str) -> ProviderEndpoint | None:
    """Read a user's provider config (decrypted); None when not configured."""
    if not user_id:
        return None
    config = await db.get_provider_config(user_id, category)
    if not config:
        return None
    api_key = ""
    if config.get("api_key_encrypted"):
        try:
            api_key = decrypt_api_key(config["api_key_encrypted"])
        except Exception:
            api_key = ""
            logger.warning(
                "Failed to decrypt %s provider API key for user %s; "
                "SECRET_KEY may have changed",
                category,
                user_id,
            )
    return ProviderEndpoint(
        provider=config.get("provider", ""),
        model=config.get("model", ""),
        api_key=api_key,
        api_base=config.get("api_base", ""),
    )

def _fallback_endpoint(
    api_key: str, api_base: str, model: str, provider: str
) -> ProviderEndpoint:
    return ProviderEndpoint(
        provider=provider, model=model, api_key=api_key, api_base=api_base
    )

def _merge_endpoint(
    user_cfg: ProviderEndpoint | None,
    fallback: ProviderEndpoint,
) -> ProviderEndpoint:
    """User config wins per-field; env defaults fill the gaps (legacy semantics)."""
    return ProviderEndpoint(
        provider=user_cfg.provider if user_cfg and user_cfg.provider else fallback.provider,
        model=user_cfg.model if user_cfg and user_cfg.model else fallback.model,
        api_key=user_cfg.api_key if user_cfg and user_cfg.api_key else fallback.api_key,
        api_base=user_cfg.api_base if user_cfg and user_cfg.api_base else fallback.api_base,
    )

async def resolve_providers(user_id: str | None) -> ProviderConfig:
    """Resolve ASR + LLM provider config (user config with env fallback).

    Env fallbacks are read lazily from ``app.config`` so tests that rebind
    the config module attributes are honored.
    """
    asr_user = await _user_endpoint(user_id, "asr")
    llm_user = await _user_endpoint(user_id, "llm")
    return ProviderConfig(
        asr=_merge_endpoint(
            asr_user,
            _fallback_endpoint(
                config.ASR_API_KEY, config.ASR_API_BASE,
                config.ASR_MODEL, config.ASR_PROVIDER,
            ),
        ),
        llm=_merge_endpoint(
            llm_user,
            _fallback_endpoint(
                config.LLM_API_KEY, config.LLM_API_BASE,
                config.LLM_MODEL, "openai",
            ),
        ),
    )

def providers_configured(provider: ProviderConfig) -> bool:
    """Return whether both ASR and LLM endpoints are complete."""
    return provider.asr.is_complete() and provider.llm.is_complete()

# --- Runtime context assembly ------------------------------------------------

class DBArtifactStore:
    """``ArtifactStore`` adapter over the ``task_artifacts`` table."""

    def __init__(self, job_id: str) -> None:
        self._job_id = job_id

    async def get(self, kind: ArtifactKind) -> object | None:
        return await db.get_artifact(self._job_id, kind.value)

    async def put(self, kind: ArtifactKind, content: object) -> None:
        await db.save_artifact(self._job_id, kind.value, content)

class _ProgressPublisher:
    """Publishes within-phase progress to the tasks row (monotonic per phase)."""

    def __init__(self, job_id: str) -> None:
        self._job_id = job_id
        self._tracker = PhaseProgressTracker()

    async def publish(self, phase: PipelinePhase, fraction: float, message: str) -> None:
        effective = self._tracker.update(phase, fraction)
        await db.update_task_status(
            self._job_id,
            "running",
            phase=phase.value,
            phase_progress=effective,
            message=message,
        )

@dataclass
class CancelHandleRegistry:
    """Per-job registry of the current stage's cancel handle."""

    handle: CancelHandle | None = None

    def registrar(self) -> CancelHandleRegistrar:
        def _register(handle: CancelHandle | None) -> None:
            self.handle = handle

        return _register

    def trigger(self) -> None:
        """Invoke the registered handle (subprocess kill), if any."""
        if self.handle is not None:
            try:
                self.handle()
            except Exception:
                logger.exception("Cancel handle raised; continuing")

async def write_user_cookiefile(user_id: str | None, url: str) -> str | None:
    """Materialize the user's per-platform cookie as a temp cookies.txt file.

    Returns None when the user has no cookie for the URL's platform. The caller
    (orchestrator) removes the file after the run.
    """
    platform = detect_video_platform(url)
    if platform not in ("youtube", "bilibili"):
        return None
    record = await db.get_user_cookie(user_id, platform)
    if not record or not record.get("cookie_encrypted"):
        return None
    try:
        cookie_content = decrypt_api_key(record["cookie_encrypted"])
    except Exception:
        logger.warning(
            "Failed to decrypt cookie for user %s platform %s", user_id, platform
        )
        return None
    if not cookie_content:
        return None
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="cookie_"
    )
    tmp.write(cookie_content)
    tmp.close()
    return tmp.name

def wav_path_for(job_id: str) -> Path:
    """The job-scoped WAV location the audio stage persists to (C2 contract)."""
    return (
        Path(tempfile.gettempdir())
        / "videonote_pipeline_audio"
        / f"{job_id}.wav"
    )

def build_stage_context(
    plan: ExecutionPlan,
    registry: CancelHandleRegistry,
    extra: dict[str, object],
) -> StageContext:
    """Assemble the runtime StageContext for one stage execution."""
    ctx = StageContext(
        job_id=plan.job_id,
        language=plan.language,
        provider=plan.provider,
        artifacts=DBArtifactStore(plan.job_id),
        progress=_ProgressPublisher(plan.job_id),
        register_cancel=registry.registrar(),
        extra={**extra},
    )
    return ctx
