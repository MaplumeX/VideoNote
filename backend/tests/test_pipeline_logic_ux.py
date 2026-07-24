"""Tests for Phase C+D+E: error detail透传, provider pre-check, ASR language,
subtitle dedup, retry file copy, safe_name hardening."""

from pathlib import Path

import pytest

from app import db
from app.api import routes
from app.auth import TokenData
from app.schemas import VideoRequest


@pytest.fixture
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    upload_dir = tmp_path / "uploads"
    database_path = upload_dir / "videonote.db"
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    monkeypatch.setattr(routes, "UPLOAD_DIR", upload_dir)
    await db.init_db()
    yield upload_dir
    await db.close_db()


# ── C1: error detail sanitization ──────────────────────────────────


def test_error_detail_sanitization() -> None:
    """API keys, Bearer tokens, and cookies are stripped from error detail."""
    # API key pattern
    exc = RuntimeError("Auth failed with key sk-abc123def456")
    detail = routes._sanitize_error_detail(exc)
    assert "sk-abc123def456" not in detail
    assert "[REDACTED]" in detail

    # Bearer token
    exc = RuntimeError("Request rejected: Bearer xyz123token")
    detail = routes._sanitize_error_detail(exc)
    assert "Bearer xyz123token" not in detail
    assert "[REDACTED]" in detail

    # Cookie content
    exc = RuntimeError("Set-Cookie: session=abc123; HttpOnly")
    detail = routes._sanitize_error_detail(exc)
    assert "session=abc123" not in detail

    # Clean message passes through
    exc = RuntimeError("Connection timeout")
    detail = routes._sanitize_error_detail(exc)
    assert detail == "Connection timeout"

    # Empty exception → empty string
    assert routes._sanitize_error_detail(RuntimeError()) == ""


def test_error_detail_truncation() -> None:
    """Detail is truncated to 200 characters."""
    long_msg = "x" * 300
    detail = routes._sanitize_error_detail(RuntimeError(long_msg))
    assert len(detail) == 200


def test_error_detail_strips_api_key_in_message_format() -> None:
    """The full message written to DB has CODE: sanitized_detail format."""
    # Simulate what _StageFailed + outer except produces
    exc = RuntimeError("Whisper error: key=sk-secretkey123456")
    detail = routes._sanitize_error_detail(exc)
    message = f"TRANSCRIPTION_FAILED: {detail}" if detail else "TRANSCRIPTION_FAILED"
    assert message.startswith("TRANSCRIPTION_FAILED")
    assert "sk-secretkey123456" not in message


# ── C4: provider pre-check ─────────────────────────────────────────


async def test_provider_not_configured(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no provider is configured, /process returns 422 PROVIDER_NOT_CONFIGURED."""
    # Ensure env fallback keys are empty
    monkeypatch.setattr(routes, "ASR_API_KEY", "")
    monkeypatch.setattr(routes, "LLM_API_KEY", "")

    request = VideoRequest(
        url="https://www.youtube.com/watch?v=abcdefghijk", language="en"
    )
    user = TokenData("user")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await routes.process_video(request, user)

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "PROVIDER_NOT_CONFIGURED"


async def test_provider_configured_allows_processing(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When provider keys exist, /process proceeds normally."""
    monkeypatch.setattr(routes, "ASR_API_KEY", "test-key")
    monkeypatch.setattr(routes, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(routes.task_runner, "schedule", lambda job_id, factory: True)

    request = VideoRequest(
        url="https://www.youtube.com/watch?v=abcdefghijk", language="en"
    )
    user = TokenData("user")

    response = await routes.process_video(request, user)
    assert response.job_id
    assert response.source_type == "url"


async def test_provider_not_configured_on_retry(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retry also checks provider configuration."""
    monkeypatch.setattr(routes, "ASR_API_KEY", "")
    monkeypatch.setattr(routes, "LLM_API_KEY", "")

    await db.create_task(
        "failed-job",
        user_id="user",
        source_type="url",
        video_url="https://www.youtube.com/watch?v=abcdefghijk",
        platform="youtube",
        language="en",
    )
    await db.update_progress("failed-job", routes.TaskStage.failed, 0.0, "VIDEO_FETCH_FAILED")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await routes.retry_task("failed-job", TokenData("user"))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "PROVIDER_NOT_CONFIGURED"


# ── D1: ASR language mapping ──────────────────────────────────────


def test_asr_language_mapping() -> None:
    assert routes._asr_language("en") == "en"
    assert routes._asr_language("zh-CN") == "zh"
    assert routes._asr_language("ja") == "ja"
    assert routes._asr_language("fr") is None
    assert routes._asr_language("de") is None


# ── D2: transcribe_audio accepts None language ────────────────────


def test_transcribe_audio_none_language_skips_language_param(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When language is None, 'language' is NOT passed to the Whisper API."""
    from unittest.mock import MagicMock

    from app.services import transcribe

    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake audio")

    mock_response = MagicMock()
    mock_response.segments = []
    mock_response.text = "hello"

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = mock_response
    monkeypatch.setattr(transcribe, "OpenAI", lambda **kwargs: mock_client)

    transcribe.transcribe_audio(str(audio_path), language=None, provider="openai")

    _, kwargs = mock_client.audio.transcriptions.create.call_args
    assert "language" not in kwargs


# ── E1: retry upload copies file ──────────────────────────────────


async def test_retry_upload_copies_file(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retry upload copies the file; old failed task's path still points to the original."""
    source = isolated_db / "source.mp4"
    source.write_bytes(b"video content")

    await db.create_task(
        "orig",
        user_id="user",
        source_type="upload",
        input_file_path=str(source),
        file_name="source.mp4",
        language="en",
    )
    await db.update_progress("orig", routes.TaskStage.failed, 0.0, "VIDEO_FETCH_FAILED")

    scheduled: list[str] = []
    monkeypatch.setattr(
        routes.task_runner, "schedule", lambda job_id, factory: scheduled.append(job_id) or True
    )
    monkeypatch.setattr(routes, "ASR_API_KEY", "test-key")
    monkeypatch.setattr(routes, "LLM_API_KEY", "test-key")

    response = await routes.retry_task("orig", TokenData("user"))
    assert response.job_id != "orig"
    assert scheduled == [response.job_id]

    new_task = await db.get_task(response.job_id)
    assert new_task is not None
    # New task has its own copy path
    new_path = Path(new_task["input_file_path"])
    assert new_path != source
    assert new_path.is_file()
    assert new_path.read_bytes() == b"video content"

    # Original failed task's file is still intact and path unchanged
    orig_task = await db.get_task("orig")
    assert orig_task is not None
    assert orig_task["input_file_path"] == str(source)
    assert source.exists()

    # If we delete the new task's copy, the original is still untouched
    new_path.unlink()
    assert source.exists()


# ── E2: sanitizer for upload filename ──────────────────────────────


def test_sanitize_upload_name_basic() -> None:
    assert routes._sanitize_upload_name("video.mp4") == "video.mp4"
    assert routes._sanitize_upload_name("my video.mkv") == "my_video.mkv"


def test_sanitize_upload_name_path_traversal() -> None:
    # Path separator replaced
    assert "/" not in routes._sanitize_upload_name("../../../etc/passwd")
    assert "\\" not in routes._sanitize_upload_name("..\\..\\secret")
    # .. collapsed
    result = routes._sanitize_upload_name("....//etc")
    assert ".." not in result


def test_sanitize_upload_name_empty_or_none() -> None:
    assert routes._sanitize_upload_name(None) == "upload"
    assert routes._sanitize_upload_name("") == "upload"
    assert routes._sanitize_upload_name("...") == "_"


def test_sanitize_upload_name_cjk_preserved() -> None:
    result = routes._sanitize_upload_name("视频文件.mp4")
    assert "视频文件" in result
    assert result.endswith(".mp4")


def test_sanitize_upload_name_takes_basename() -> None:
    # Even if a path is passed, only the basename is used
    result = routes._sanitize_upload_name("/tmp/uploads/../../etc/shadow")
    assert "/" not in result
    assert "\\" not in result