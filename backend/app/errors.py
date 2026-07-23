"""Structured error detail helper for i18n-ready API errors.

HTTPException(detail=error_detail("INVALID_CREDENTIALS")) returns:
    {"detail": {"code": "INVALID_CREDENTIALS"}}

With interpolation params:
    error_detail("TASK_WITH_ID_NOT_FOUND", jobId="abc")
    -> {"detail": {"code": "TASK_WITH_ID_NOT_FOUND", "params": {"jobId": "abc"}}}

Frontend maps `code` to a translation key `errors.<camelCase>` and interpolates
`params` into the translated string.
"""

from typing import Any


def error_detail(code: str, **params: Any) -> dict[str, Any]:
    """Build a structured error detail dict from an error code and optional params."""
    detail: dict[str, Any] = {"code": code}
    if params:
        detail["params"] = params
    return detail