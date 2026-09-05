"""Task state machine: status/phase enums, paths, transitions, and checkpoints.

Core semantic change vs. the legacy single ``TaskStage`` enum: task lifecycle
status (``TaskStatus``) and the processing phase within a run (``PipelinePhase``)
are now separate. Terminal states (failed/cancelled/complete) live on
``TaskStatus``; ``PipelinePhase`` only names execution phases. This split makes
transition validation possible and is the contract source for C2~C5 and the
frontend.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.pipeline.errors import InvalidTransitionError


class TaskStatus(StrEnum):
    """Task lifecycle status (the *task-level* dimension)."""

    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"
    cancelled = "cancelled"


TERMINAL_STATUSES = frozenset(
    {TaskStatus.complete, TaskStatus.failed, TaskStatus.cancelled}
)


class PipelinePhase(StrEnum):
    """Execution phase within a running task (the *phase-level* dimension)."""

    fetching = "fetching"
    subtitle = "subtitle"
    audio = "audio"
    transcribe = "transcribe"
    notegen = "notegen"


class ArtifactKind(StrEnum):
    """Kinds of intermediate artifacts persisted in ``task_artifacts``."""

    video_meta = "video_meta"
    subtitle = "subtitle"
    transcript = "transcript"
    notes_draft = "notes_draft"  # Reserved for C3 multi-chunk intermediate state.


URL_PATH: tuple[PipelinePhase, ...] = (
    PipelinePhase.fetching,
    PipelinePhase.subtitle,
    PipelinePhase.audio,
    PipelinePhase.transcribe,
    PipelinePhase.notegen,
)

FILE_PATH: tuple[PipelinePhase, ...] = (
    PipelinePhase.audio,
    PipelinePhase.transcribe,
    PipelinePhase.notegen,
)

Path = tuple[PipelinePhase, ...]

# Transition table: source phase (None = start) -> allowed next phases.
# Phase-level only. Terminal statuses (failed/cancelled) are reached from ANY
# phase and are validated at the TaskStatus level, not here.
# - subtitle -> notegen models the subtitle-hit skip (audio+transcribe bypass).
# - notegen -> None models normal completion (transition to nothing).
ALLOWED_TRANSITIONS: dict[PipelinePhase | None, frozenset[PipelinePhase]] = {
    None: frozenset({PipelinePhase.fetching, PipelinePhase.audio}),
    PipelinePhase.fetching: frozenset({PipelinePhase.subtitle}),
    PipelinePhase.subtitle: frozenset(
        {PipelinePhase.audio, PipelinePhase.notegen}
    ),  # miss -> audio; hit -> notegen (skip)
    PipelinePhase.audio: frozenset({PipelinePhase.transcribe}),
    PipelinePhase.transcribe: frozenset({PipelinePhase.notegen}),
    PipelinePhase.notegen: frozenset(),  # terminal: task completes
}


def validate_transition(src: PipelinePhase | None, dst: PipelinePhase) -> None:
    """Validate a phase transition, raising ``InvalidTransitionError`` if illegal.

    ``src=None`` denotes task start; ``dst=None`` (notegen completing) is
    modeled by the empty allowed-set at ``notegen``, so completing is *not*
    an error — call ``validate_completion`` for that check instead.
    """
    allowed = ALLOWED_TRANSITIONS.get(src)
    if allowed is None:
        raise InvalidTransitionError(
            f"Unknown source phase: {src!r}", src=src, dst=dst
        )
    if dst not in allowed:
        raise InvalidTransitionError(
            f"Illegal transition: {src!r} -> {dst!r}", src=src, dst=dst
        )


def validate_completion(phase: PipelinePhase) -> None:
    """Validate that a phase may complete the pipeline (only ``notegen`` may)."""
    if ALLOWED_TRANSITIONS.get(phase) is None:
        raise InvalidTransitionError(
            f"Unknown phase: {phase!r}", src=phase, dst=None
        )
    if ALLOWED_TRANSITIONS[phase]:
        raise InvalidTransitionError(
            f"Phase {phase!r} cannot complete the pipeline; "
            f"expected one of {sorted(ALLOWED_TRANSITIONS[phase])}",
            src=phase,
            dst=None,
        )


def next_phases(path: Path, current: PipelinePhase | None) -> tuple[PipelinePhase, ...]:
    """Return the phases reachable from ``current`` within ``path``.

    ``current=None`` means the task has not started; the result is the path's
    valid starting phases (intersected with the transition table).
    """
    if current is None:
        starts = ALLOWED_TRANSITIONS[None]
        return tuple(p for p in path if p in starts)
    if current not in path:
        raise ValueError(
            f"Phase {current!r} is not part of path {[p.value for p in path]}"
        )
    allowed = ALLOWED_TRANSITIONS[current]
    return tuple(p for p in path if p in allowed)



@dataclass(frozen=True)
class Checkpoint:
    """Point-in-time resume state persisted per task.

    ``completed_phase`` is the last phase that finished successfully with its
    outputs persisted. ``artifacts`` records which artifact kinds are already
    durably stored for the job.
    """

    completed_phase: PipelinePhase
    artifacts: frozenset[ArtifactKind] = frozenset()


def resume_point(path: Path, checkpoint: Checkpoint | None) -> PipelinePhase:
    """Compute the phase to (re)start from given a checkpoint.

    Rules:
    - No checkpoint -> first phase of the path.
    - Subtitle artifact present -> skip audio+transcribe, resume at notegen
      (the conditional skip expressed jointly by the transition table and
      artifact presence).
    - Otherwise -> first allowed successor of ``completed_phase`` within the
      path. If the completed phase was the last one (notegen), the task is
      done; return notegen's value and let the caller decide (orphan recovery
      re-runs the final cheap check).
    """
    if checkpoint is None:
        return path[0]

    # Subtitle hit: transition table allows subtitle -> notegen; artifact
    # presence confirms the hit, so audio/transcribe are skipped entirely.
    if ArtifactKind.subtitle in checkpoint.artifacts:
        if PipelinePhase.notegen not in path:
            raise ValueError(
                "Subtitle artifact present but path has no notegen phase"
            )
        return PipelinePhase.notegen

    successors = next_phases(path, checkpoint.completed_phase)
    if successors:
        return successors[0]
    # completed_phase exhausted the path (e.g. notegen on a re-dispatch after
    # success): re-run the final phase so the terminal write is idempotent.
    return checkpoint.completed_phase
