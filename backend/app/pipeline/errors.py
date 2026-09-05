"""Unified pipeline error codes, ``PipelineError``, and centralized sanitization.

Sanitization is structural: ``PipelineError`` sanitizes its ``detail`` at
construction time, so any layer that later reads ``error.detail`` gets an
already-safe string. Forgetting to sanitize is impossible by construction.
"""

from __future__ import annotations

import re
from enum import StrEnum

# --- Sanitization patterns (migrated from app.api.routes._sanitize_error_detail) ---

_API_KEY_RE = re.compile(r"sk-[A-Za-z0-9-_]{8,}")
_BEARER_RE = re.compile(r"[Bb]earer\s+[A-Za-z0-9\-_.=]+")
_COOKIE_RE = re.compile(r"(?:set-)?cookie:\s*[^\n;]+", re.IGNORECASE)

MAX_DETAIL_LENGTH = 200


def sanitize_detail(text: str) -> str:
    """Strip sensitive data (API keys, Bearer tokens, cookies) from text.

    Returns a sanitized string truncated to 200 characters, or empty string.
    """
    raw = text
    raw = _API_KEY_RE.sub("[REDACTED]", raw)
    raw = _BEARER_RE.sub("[REDACTED]", raw)
    raw = _COOKIE_RE.sub("[REDACTED]", raw)
    raw = raw.strip()
    if len(raw) > MAX_DETAIL_LENGTH:
        raw = raw[:MAX_DETAIL_LENGTH]
    return raw


class ErrorCode(StrEnum):
    """Unified pipeline error codes.

    Video-fetch codes mirror the semantics of ``classify_ytdlp_error`` in
    ``app/services/subtitle.py``. Non-pipeline codes (e.g.
    ``MODELS_FETCH_FAILED``) stay in ``app/errors.py`` and are not migrated.
    """

    # Video fetch (yt-dlp classification)
    VIDEO_PRIVATE = "VIDEO_PRIVATE"
    VIDEO_GEO_RESTRICTED = "VIDEO_GEO_RESTRICTED"
    VIDEO_NOT_FOUND = "VIDEO_NOT_FOUND"
    VIDEO_COOKIE_INVALID = "VIDEO_COOKIE_INVALID"
    VIDEO_FETCH_FAILED = "VIDEO_FETCH_FAILED"

    # Stage failures
    SUBTITLE_EXTRACTION_FAILED = "SUBTITLE_EXTRACTION_FAILED"
    AUDIO_EXTRACTION_FAILED = "AUDIO_EXTRACTION_FAILED"
    TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
    NOTE_GENERATION_FAILED = "NOTE_GENERATION_FAILED"

    # Task / system
    PROCESSING_FAILED = "PROCESSING_FAILED"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    TASK_RECOVERY_MAX_ATTEMPTS = "TASK_RECOVERY_MAX_ATTEMPTS"
    TASK_RECOVERY_INPUT_INVALID = "TASK_RECOVERY_INPUT_INVALID"
    TASK_RECOVERY_UNSUPPORTED_URL = "TASK_RECOVERY_UNSUPPORTED_URL"
    TASK_CANCELLED = "TASK_CANCELLED"


class InvalidTransitionError(Exception):
    """Raised when a phase transition violates the state machine."""

    def __init__(self, message: str, *, src: object, dst: object) -> None:
        super().__init__(message)
        self.src = src
        self.dst = dst


class PipelineError(Exception):
    """Pipeline failure with a stable error code and a sanitized detail.

    ``detail`` is sanitized (and truncated) at construction; reading
    ``error.detail`` afterwards is always safe for persistence/UI. Raw
    exception text must stay in server logs only.
    """

    def __init__(
        self,
        code: ErrorCode,
        *,
        detail: str = "",
        cause: BaseException | None = None,
    ) -> None:
        sanitized = sanitize_detail(detail)
        super().__init__(f"{code.value}: {sanitized}" if sanitized else code.value)
        self.code = code
        self.detail = sanitized
        if cause is not None:
            self.__cause__ = cause
