"""Markdown normalization helpers for generated notes."""

from __future__ import annotations

import re

_OUTER_MARKDOWN_FENCE_RE = re.compile(
    r"\A[ \t]*```(?:markdown|md|mkd)?[ \t]*\r?\n(?P<body>.*)\r?\n[ \t]*```[ \t]*\Z",
    re.DOTALL | re.IGNORECASE,
)


def normalize_note_markdown(markdown: str) -> str:
    """Remove an outer Markdown code fence when it wraps the entire note."""
    stripped = markdown.strip()
    match = _OUTER_MARKDOWN_FENCE_RE.fullmatch(stripped)
    if not match:
        return markdown
    return match.group("body").strip()
