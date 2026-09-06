"""Two-level progress model: stage (phase) + within-phase fraction.

The global 0-1 percentage is abolished. A frontend that wants a total
progress bar can synthesize it as ``(phase_index + fraction) / phase_count``
per path; the backend no longer maintains global magic ranges (see
docs/pipeline-contract.md).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from app.pipeline.state import PipelinePhase, TaskStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProgressEvent:
    """SSE progress event payload (serialized as JSON by the API layer)."""

    status: TaskStatus
    phase: PipelinePhase | None  # None when status is pending/terminal
    phase_progress: float  # within-phase fraction, clamped to [0, 1]
    message: str  # display text or error code
    attempt: int
    timestamp: str  # ISO 8601

    @staticmethod
    def now(
        status: TaskStatus,
        phase: PipelinePhase | None,
        phase_progress: float,
        message: str,
        attempt: int,
    ) -> ProgressEvent:
        """Build an event stamped with the current UTC time."""
        return ProgressEvent(
            status=status,
            phase=phase,
            phase_progress=max(0.0, min(1.0, phase_progress)),
            message=message,
            attempt=attempt,
            timestamp=datetime.now(UTC).isoformat(),
        )


@runtime_checkable
class ProgressPublisher(Protocol):
    """Publishes within-phase progress for a running task."""

    async def publish(
        self, phase: PipelinePhase, fraction: float, message: str
    ) -> None: ...


class PhaseProgressTracker:
    """Within-phase monotonic guard.

    For the same phase, ``fraction`` only ever moves up (a regression is
    clamped to the running max with a warning log). Switching to a new phase
    resets the guard. ``update`` returns the effective (clamped, monotonic)
    fraction the caller should publish.
    """

    def __init__(self) -> None:
        self._phase: PipelinePhase | None = None
        self._max_fraction: float = 0.0

    @property
    def phase(self) -> PipelinePhase | None:
        """Current phase being tracked."""
        return self._phase

    @property
    def max_fraction(self) -> float:
        """Highest fraction seen for the current phase."""
        return self._max_fraction

    def update(self, phase: PipelinePhase, fraction: float) -> float:
        """Clamp ``fraction`` to [0, 1] and enforce within-phase monotonicity.

        Returns the effective fraction to publish. A phase switch resets the
        running max; a regression within the same phase returns the max and
        logs a warning.
        """
        clamped = max(0.0, min(1.0, fraction))
        if phase != self._phase:
            self._phase = phase
            self._max_fraction = clamped
            return clamped
        if clamped < self._max_fraction:
            logger.warning(
                "Phase progress regression for %s: %s < %s; using max",
                phase.value,
                clamped,
                self._max_fraction,
            )
            return self._max_fraction
        self._max_fraction = clamped
        return clamped
