"""Tests for the core note pipeline bug fixes (R1–R6)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import db
from app.api import routes
from app.auth import TokenData
from app.schemas import VideoRequest
from app.services import note_gen, subtitle, transcribe

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

    monkeypatch.setattr(routes, "get_video_info_strict", fake_get_video_info)
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
    assert task["message"] == "AUDIO_EXTRACTION_FAILED"
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

MAX_SENTINEL_SIZE = 100 * 1024 * 1024  # 100MB > openAI limit, forces chunk path


# ── Fix A: ASR chunk timestamp offset ───────────────────────────────


def test_shift_timestamps_adds_chunk_offset() -> None:
    text = "[00:00:10](#t=10) first\n[00:00:20](#t=20) second"
    shifted = transcribe._shift_timestamps(text, 600.0)
    assert "[00:10:10](#t=610) first" in shifted
    assert "[00:10:20](#t=620) second" in shifted


def test_shift_timestamps_passthrough_no_timestamps() -> None:
    text = "纯文本没有任何时间戳\nsecond line"
    assert transcribe._shift_timestamps(text, 600.0) == text


def test_transcribe_large_file_offsets_chunk_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio_path = tmp_path / "big.wav"
    audio_path.write_bytes(b"fake large audio")

    fixed_chunk_transcript = "[00:00:10](#t=10) a\n[00:00:20](#t=20) b"
    monkeypatch.setattr(
        transcribe,
        "_transcribe_file",
        lambda *a, **k: fixed_chunk_transcript,
    )

    call_args: list[list[str]] = []

    def fake_subprocess_run(cmd, *args, **kwargs):
        call_args.append(cmd)
        result = MagicMock()
        if cmd and cmd[0] == "ffprobe":
            result.stdout = "1200.0\n"
        result.returncode = 0
        return result

    monkeypatch.setattr(transcribe.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(transcribe.os.path, "getsize", lambda p: MAX_SENTINEL_SIZE)

    client = MagicMock()
    transcript = transcribe._transcribe_large_file(
        client, str(audio_path), "en", "whisper-1", "openai"
    )

    # ffprobe + several ffmpeg chunk splits (chunk_duration = min(1200*ratio, 600)).
    ffmpeg_cmds = [c for c in call_args if c[0] == "ffmpeg"]
    assert len(ffmpeg_cmds) >= 2
    # Extract the -ss offset for each chunk.
    starts = [float(c[c.index("-ss") + 1]) for c in ffmpeg_cmds]
    lines = transcript.splitlines()
    # First chunk (offset 0) keeps relative timestamps.
    assert "[00:00:10](#t=10) a" in lines
    assert "[00:00:20](#t=20) b" in lines
    # Every subsequent chunk must carry its start offset.
    for start in starts:
        if start == 0.0:
            continue
        shifted_seconds = int(10 + start)
        assert transcribe._format_timestamp(10 + start) in transcript
        assert f"#t={shifted_seconds}" in transcript


# ── Fix C: note generation robustness ────────────────────────────────


def test_generate_notes_max_tokens_is_8192(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="# Notes"))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(note_gen, "OpenAI", lambda **kwargs: mock_client)

    note_gen.generate_notes("short transcript")

    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["max_tokens"] == 8192


def test_generate_notes_splits_long_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R9: long transcripts are chunked, not truncated."""
    # Build a transcript with many short lines so _split_transcript can split at
    # line boundaries.
    line = "[00:00:01](#t=1) some content here\n"
    # Enough lines to exceed MAX_TRANSCRIPT_CHARS multiple times.
    lines_needed = (note_gen.MAX_TRANSCRIPT_CHARS // len(line)) + 10
    long_transcript = (line * lines_needed).rstrip("\n")

    chunks = note_gen._split_transcript(long_transcript)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= note_gen.MAX_TRANSCRIPT_CHARS

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="# Notes"))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr(note_gen, "OpenAI", lambda **kwargs: mock_client)

    note_gen.generate_notes(long_transcript)

    # One call per chunk + one merge call.
    assert mock_client.chat.completions.create.call_count == len(chunks) + 1

    # No single user message should contain the entire transcript.
    for call in mock_client.chat.completions.create.call_args_list:
        _, kwargs = call
        user_content = kwargs["messages"][1]["content"]
        assert len(user_content) < len(long_transcript)


# ── Phase F: duplicate submit dedupe ─────────────────────────────────


async def test_find_active_task_by_url_returns_active_task(
    isolated_db: Path,
) -> None:
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    await db.create_task(
        "job-1",
        user_id="user",
        video_url=url,
        platform="youtube",
        source_type="url",
    )
    # Terminal task should be ignored
    await db.create_task(
        "job-2",
        user_id="user",
        video_url=url,
        platform="youtube",
        source_type="url",
    )
    await db.set_result("job-2", "# done")
    # Cancelled task should be ignored
    await db.create_task(
        "job-3",
        user_id="user",
        video_url=url,
        platform="youtube",
        source_type="url",
    )
    await db.request_task_cancel("job-3", user_id="user")

    found = await db.find_active_task_by_url("user", url)
    assert found is not None
    assert found["job_id"] == "job-1"

    # Different user → no match
    assert await db.find_active_task_by_url("other", url) is None

    # Different URL → no match
    assert await db.find_active_task_by_url("user", "https://other.com") is None


async def test_process_video_dedupes_active_task(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    await db.create_task(
        "existing",
        user_id="user",
        video_url=url,
        platform="youtube",
        source_type="url",
    )
    monkeypatch.setattr(routes.task_runner, "schedule", lambda job_id, factory: True)

    request = VideoRequest(url=url, language="en")
    response = await routes.process_video(request, TokenData("user"))

    assert response.job_id == "existing"
    # No new task should have been created
    tasks = await db.get_user_tasks("user")
    assert len(tasks) == 1


async def test_process_video_does_not_dedupe_terminal_task(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    await db.create_task(
        "completed",
        user_id="user",
        video_url=url,
        platform="youtube",
        source_type="url",
    )
    await db.set_result("completed", "# done")
    monkeypatch.setattr(routes.task_runner, "schedule", lambda job_id, factory: True)

    request = VideoRequest(url=url, language="en")
    response = await routes.process_video(request, TokenData("user"))

    assert response.job_id != "completed"
    tasks = await db.get_user_tasks("user")
    assert len(tasks) == 2


# ── Phase G: /models error leakage ──────────────────────────────────


async def test_models_endpoint_returns_stable_error_code(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The /models endpoint must not leak internal exception text."""
    from app.schemas import ModelsRequest

    # Force the OpenAI import to fail with a sensitive error
    def bad_async_openai(**kwargs):
        raise RuntimeError("Connection refused to https://internal.api.com key=sk-leaked")

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", bad_async_openai)

    req = ModelsRequest(api_key="sk-test", api_base="https://api.test.com/v1", category="llm")
    response = await routes.list_models(req, TokenData("user"))

    assert response.error == "MODELS_FETCH_FAILED"
    assert response.models == []
    # Ensure no leakage of internal details
    assert "sk-leaked" not in (response.error or "")
    assert "internal.api.com" not in (response.error or "")


# ── Phase D: recovery attempt limit ───────────────────────────────


async def test_recover_incomplete_tasks_marks_over_limit_failed(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tasks exceeding MAX_TASK_ATTEMPTS are marked failed during recovery."""
    from app.db import MAX_TASK_ATTEMPTS

    await db.create_task(
        "over-limit",
        user_id="user",
        video_url="https://www.youtube.com/watch?v=abc123",
        platform="youtube",
        source_type="url",
        language="en",
    )
    # Bump attempt_count to MAX_TASK_ATTEMPTS
    for _ in range(MAX_TASK_ATTEMPTS):
        await db.increment_attempt("over-limit")

    scheduled: list[str] = []
    monkeypatch.setattr(
        routes.task_runner, "schedule",
        lambda job_id, factory: scheduled.append(job_id) or True,
    )

    await routes.recover_incomplete_tasks()

    assert scheduled == []
    task = await db.get_task("over-limit")
    assert task is not None
    assert task["stage"] == "failed"
    assert task["message"] == "TASK_RECOVERY_MAX_ATTEMPTS"


# ── Phase E: truncation continuation ───────────────────────────────


def test_generate_notes_continues_on_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM output truncated by max_tokens is detected and continued."""
    truncated_response = MagicMock()
    truncated_response.choices = [
        MagicMock(
            message=MagicMock(content="# Title\n"),
            finish_reason="length",
        )
    ]

    continued_response = MagicMock()
    continued_response.choices = [
        MagicMock(
            message=MagicMock(content="## Section"),
            finish_reason="stop",
        )
    ]

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        truncated_response, continued_response,
    ]
    monkeypatch.setattr(note_gen, "OpenAI", lambda **kwargs: mock_client)

    result = note_gen._call_llm(
        mock_client,
        [{"role": "user", "content": "test"}],
        "test-model",
    )

    assert "# Title" in result
    assert "## Section" in result
    assert mock_client.chat.completions.create.call_count == 2
