"""Tests for the core note pipeline bug fixes (R1–R6)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import db
from app.api import routes
from app.auth import TokenData
from app.schemas import VideoRequest
from app.services import subtitle, transcribe

# ── D1: _srt_to_transcript ──────────────────────────────────────────


def test_srt_to_transcript_produces_timestamp_links() -> None:
    raw = (
        "1\n"
        "00:00:01,500 --> 00:00:04,000\n"
        "Hello world\n"
        "\n"
        "2\n"
        "00:00:05,000 --> 00:00:08,000\n"
        "Second line\n"
    )
    result = subtitle._srt_to_transcript(raw)
    assert result is not None
    assert "[00:00:01](#t=1) Hello world" in result
    assert "[00:00:05](#t=5) Second line" in result


def test_vtt_to_transcript_produces_timestamp_links() -> None:
    raw = (
        "WEBVTT\n"
        "\n"
        "00:00:01.000 --> 00:00:03.000\n"
        "First cue\n"
        "\n"
        "00:00:04.500 --> 00:00:06.000 position:10% align:start\n"
        "Second cue\n"
    )
    result = subtitle._srt_to_transcript(raw)
    assert result is not None
    assert "[00:00:01](#t=1) First cue" in result
    assert "[00:00:04](#t=4) Second cue" in result


def test_vtt_multiline_cue_joined_with_space() -> None:
    raw = (
        "00:00:01.000 --> 00:00:03.000\n"
        "First line\n"
        "Second line\n"
    )
    result = subtitle._srt_to_transcript(raw)
    assert result is not None
    assert "[00:00:01](#t=1) First line Second line" in result


def test_srt_to_transcript_returns_none_for_malformed() -> None:
    assert subtitle._srt_to_transcript("") is None
    assert subtitle._srt_to_transcript("not a subtitle") is None
    assert subtitle._srt_to_transcript("WEBVTT\n\nNOTE just a note") is None


# ── D2: transcribe_audio receives language ─────────────────────────


def test_transcribe_audio_passes_language_to_whisper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fake audio")

    mock_response = MagicMock()
    mock_response.segments = []
    mock_response.text = "hello"

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = mock_response

    monkeypatch.setattr(transcribe, "OpenAI", lambda **kwargs: mock_client)

    transcribe.transcribe_audio(str(audio_path), language="en", provider="openai")

    _, kwargs = mock_client.audio.transcriptions.create.call_args
    assert kwargs.get("language") == "en"


def test_transcribe_audio_defaults_to_en(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default language should be "en", not "zh"
    mock_response = MagicMock()
    mock_response.segments = []
    mock_response.text = "hello"

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = mock_response
    monkeypatch.setattr(transcribe, "OpenAI", lambda **kwargs: mock_client)

    import inspect

    sig = inspect.signature(transcribe.transcribe_audio)
    assert sig.parameters["language"].default == "en"


# ── D3: process_video returns without calling get_video_info ────────


@pytest.fixture
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    upload_dir = tmp_path / "uploads"
    database_path = upload_dir / "videonote.db"
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    monkeypatch.setattr(routes, "UPLOAD_DIR", upload_dir)
    await db.init_db()
    return upload_dir


async def test_process_video_does_not_call_get_video_info(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_info_calls: list[tuple] = []

    def fake_get_video_info(*args, **kwargs):
        get_info_calls.append(args)
        return {"title": "should not be called", "thumbnail_url": None}

    monkeypatch.setattr(routes, "get_video_info", fake_get_video_info)
    monkeypatch.setattr(routes.task_runner, "schedule", lambda job_id, factory: True)

    request = VideoRequest(
        url="https://www.youtube.com/watch?v=abcdefghijk", language="en"
    )
    user = TokenData("user")

    response = await routes.process_video(request, user)

    assert get_info_calls == []
    assert response.job_id
    assert response.title == ""
    assert response.thumbnail_url == ""
    assert response.platform == "youtube"

    task = await db.get_task(response.job_id)
    assert task is not None
    assert task["source_type"] == "url"


# ── D4: failed upload task retains file ─────────────────────────────


async def test_failed_upload_task_retains_file(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = isolated_db / "source.mp4"
    source.write_bytes(b"video")

    await db.create_task(
        "fail-job",
        user_id="user",
        source_type="upload",
        input_file_path=str(source),
    )

    async def fake_to_thread(function, *args, **kwargs):
        if function is routes.extract_audio:
            raise RuntimeError("ffmpeg crashed")
        raise AssertionError("unexpected to_thread call")

    monkeypatch.setattr(routes.asyncio, "to_thread", fake_to_thread)

    await routes._process_video_file("fail-job", str(source), user_id="user")

    task = await db.get_task("fail-job")
    assert task is not None
    assert task["stage"] == "failed"
    assert task["message"] == "VIDEO_FETCH_FAILED"
    # File should still exist for retry
    assert source.exists()
    assert task["input_file_path"] is not None


# ── D5: retry_task works for upload tasks ───────────────────────────


async def test_retry_task_for_upload_reuses_file(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = isolated_db / "source.mp4"
    source.write_bytes(b"video")

    await db.create_task(
        "orig",
        user_id="user",
        source_type="upload",
        input_file_path=str(source),
        file_name="source.mp4",
        language="en",
    )
    # Mark as failed so retry is allowed
    await db.update_progress("orig", routes.TaskStage.failed, 0.0, "VIDEO_FETCH_FAILED")

    scheduled: list[str] = []
    monkeypatch.setattr(
        routes.task_runner, "schedule", lambda job_id, factory: scheduled.append(job_id) or True
    )

    response = await routes.retry_task("orig", TokenData("user"))

    assert response.job_id != "orig"
    assert response.title == ""
    assert response.thumbnail_url == ""
    assert scheduled == [response.job_id]

    new_task = await db.get_task(response.job_id)
    assert new_task is not None
    assert new_task["source_type"] == "upload"
    assert new_task["input_file_path"] == str(source)


async def test_retry_upload_missing_file_raises(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await db.create_task(
        "missing",
        user_id="user",
        source_type="upload",
        input_file_path=str(isolated_db / "deleted.mp4"),
        language="en",
    )
    await db.update_progress("missing", routes.TaskStage.failed, 0.0, "VIDEO_FETCH_FAILED")

    monkeypatch.setattr(routes.task_runner, "schedule", lambda job_id, factory: True)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await routes.retry_task("missing", TokenData("user"))

    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "UPLOAD_FILE_MISSING"


# ── D6: failed-task message is a stable error code ──────────────────


async def test_transcription_failure_uses_stable_code(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = isolated_db / "source.mp4"
    source.write_bytes(b"video")

    await db.create_task(
        "transcribe-fail",
        user_id="user",
        source_type="upload",
        input_file_path=str(source),
    )

    async def fake_to_thread(function, *args, **kwargs):
        if function is routes.extract_audio:
            return None  # succeed audio extraction
        if function is routes.transcribe_audio:
            raise RuntimeError("Whisper API error: 500 Internal Server Error")
        raise AssertionError("unexpected to_thread call")

    monkeypatch.setattr(routes.asyncio, "to_thread", fake_to_thread)

    await routes._process_video_file(
        "transcribe-fail", str(source), language="en", user_id="user"
    )

    task = await db.get_task("transcribe-fail")
    assert task is not None
    assert task["stage"] == "failed"
    # Message must be a stable code, not raw exception text
    assert task["message"] == "TRANSCRIPTION_FAILED"
    assert "Whisper" not in task["message"]
    assert "500" not in task["message"]


async def test_note_generation_failure_uses_stable_code(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = isolated_db / "source.mp4"
    source.write_bytes(b"video")

    await db.create_task(
        "gen-fail",
        user_id="user",
        source_type="upload",
        input_file_path=str(source),
    )

    call_count = 0

    async def fake_to_thread(function, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if function is routes.extract_audio:
            return None
        if function is routes.transcribe_audio:
            return "transcript text"
        if function is routes.generate_notes:
            raise RuntimeError("LLM API timeout with sensitive key=sk-xxxx")
        raise AssertionError("unexpected to_thread call")

    monkeypatch.setattr(routes.asyncio, "to_thread", fake_to_thread)

    await routes._process_video_file(
        "gen-fail", str(source), language="en", user_id="user"
    )

    task = await db.get_task("gen-fail")
    assert task is not None
    assert task["stage"] == "failed"
    assert task["message"] == "NOTE_GENERATION_FAILED"
    assert "sk-xxxx" not in task["message"]


# ── B1: _asr_language mapping ──────────────────────────────────────


def test_asr_language_mapping() -> None:
    assert routes._asr_language("en") == "en"
    assert routes._asr_language("zh-CN") == "zh"
    assert routes._asr_language("zh-TW") == "zh"