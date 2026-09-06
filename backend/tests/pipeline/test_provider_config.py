"""Provider-config and misc DB utility tests (C4), extracted from the legacy suites.

Covers: /models stable error code (no leak), the SQLite timestamp-format
guards (``_sqlite_utc_timestamp``), and the decrypt-failure warning path in
provider config resolution (now living in pipeline/context.py).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app import db
from app.auth import TokenData


@pytest.fixture
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    upload_dir = tmp_path / "uploads"
    database_path = upload_dir / "videonote.db"
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    await db.init_db()
    yield upload_dir
    await db.close_db()


async def test_models_endpoint_returns_stable_error_code(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The /models endpoint must not leak internal exception text."""
    def bad_async_client(**kwargs):
        raise RuntimeError("Connection refused to https://internal.api.com key=sk-leaked")

    import openai

    monkeypatch.setattr(openai, "AsyncClient", bad_async_client)

    from app.api import provider_routes
    from app.schemas import ModelsRequest

    req = ModelsRequest(api_key="sk-test", api_base="https://api.test.com/v1", category="llm")
    response = await provider_routes.list_models(req, TokenData("user"))

    assert response.error == "MODELS_FETCH_FAILED"
    assert response.models == []
    assert "sk-leaked" not in (response.error or "")
    assert "internal.api.com" not in (response.error or "")


def test_sqlite_utc_timestamp_format() -> None:
    now = datetime(2025, 9, 2, 12, 0, 0, tzinfo=UTC)
    cutoff = db._sqlite_utc_timestamp(now - timedelta(days=7))
    assert cutoff == "2025-08-26 12:00:00"
    assert "T" not in cutoff
    assert "+" not in cutoff

    same_instant = db._sqlite_utc_timestamp(now)
    assert not (same_instant < cutoff)  # type: ignore[operator]

    older = db._sqlite_utc_timestamp(now - timedelta(days=8))
    assert older < cutoff  # type: ignore[operator]


def test_sqlite_current_timestamp_string_comparison() -> None:
    created = "2025-09-02 12:00:00"
    iso_cutoff = "2025-09-02T12:00:00+00:00"
    assert created < iso_cutoff
    sqlite_cutoff = db._sqlite_utc_timestamp(datetime(2025, 9, 2, 12, 0, 0, tzinfo=UTC))
    assert not (created < sqlite_cutoff)


async def test_provider_resolution_logs_warning_on_decrypt_failure(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A garbage-encrypted key must degrade to empty and log a warning."""
    from app.pipeline import context as pipeline_context

    await db.create_user("user-1", "user-1@example.com", "hash")
    await db.save_provider_config(
        user_id="user-1",
        category="llm",
        provider="openai",
        model="gpt-4o",
        api_key_encrypted="not-encrypted-garbage",
        api_base="https://api.test.com/v1",
    )

    def broken_decrypt(value: str) -> str:
        raise ValueError("bad fernet token")

    monkeypatch.setattr(pipeline_context, "decrypt_api_key", broken_decrypt)

    with caplog.at_level(logging.WARNING, logger="app.pipeline.context"):
        provider = await pipeline_context.resolve_providers("user-1")

    assert provider.llm.api_key == ""
    warnings = [r for r in caplog.records if "user-1" in r.message and "llm" in r.message]
    assert warnings, "expected a decrypt-failure warning mentioning user and category"
    assert any("SECRET_KEY" in r.message for r in warnings)
