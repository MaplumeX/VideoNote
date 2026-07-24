"""Tests for R4/R7/R8/R9/R10: terminal cleanup, DB lock, provider validation,
retry platform, LIKE escape."""

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


# ── R8: provider config validates model/api_base ──────────────────


async def test_provider_not_configured_when_model_empty(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When api_key exists but model is empty, /process returns 422."""
    monkeypatch.setattr(routes, "ASR_API_KEY", "test-key")
    monkeypatch.setattr(routes, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(routes, "ASR_MODEL", "whisper-1")
    monkeypatch.setattr(routes, "LLM_MODEL", "")
    monkeypatch.setattr(routes, "ASR_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setattr(routes, "LLM_API_BASE", "https://api.openai.com/v1")

    from fastapi import HTTPException

    request = VideoRequest(
        url="https://www.youtube.com/watch?v=abcdefghijk", language="en"
    )
    with pytest.raises(HTTPException) as exc_info:
        await routes.process_video(request, TokenData("user"))
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "PROVIDER_NOT_CONFIGURED"


async def test_provider_not_configured_when_api_base_empty(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When api_key exists but api_base is empty, /process returns 422."""
    monkeypatch.setattr(routes, "ASR_API_KEY", "test-key")
    monkeypatch.setattr(routes, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(routes, "ASR_MODEL", "whisper-1")
    monkeypatch.setattr(routes, "LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(routes, "ASR_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setattr(routes, "LLM_API_BASE", "")

    from fastapi import HTTPException

    request = VideoRequest(
        url="https://www.youtube.com/watch?v=abcdefghijk", language="en"
    )
    with pytest.raises(HTTPException) as exc_info:
        await routes.process_video(request, TokenData("user"))
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "PROVIDER_NOT_CONFIGURED"


async def test_provider_configured_with_all_fields(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When all provider fields are set, /process proceeds normally."""
    monkeypatch.setattr(routes, "ASR_API_KEY", "test-key")
    monkeypatch.setattr(routes, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(routes, "ASR_MODEL", "whisper-1")
    monkeypatch.setattr(routes, "LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(routes, "ASR_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setattr(routes, "LLM_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setattr(routes.task_runner, "schedule", lambda job_id, factory: True)

    response = await routes.process_video(
        VideoRequest(
            url="https://www.youtube.com/watch?v=abcdefghijk", language="en"
        ),
        TokenData("user"),
    )
    assert response.job_id


# ── R9: retry upload platform is not "upload" ─────────────────────


async def test_retry_upload_platform_empty(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retry upload returns empty platform, not 'upload'."""
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

    monkeypatch.setattr(routes.task_runner, "schedule", lambda job_id, factory: True)
    monkeypatch.setattr(routes, "ASR_API_KEY", "test-key")
    monkeypatch.setattr(routes, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(routes, "ASR_MODEL", "whisper-1")
    monkeypatch.setattr(routes, "LLM_MODEL", "gpt-4o")
    monkeypatch.setattr(routes, "ASR_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setattr(routes, "LLM_API_BASE", "https://api.openai.com/v1")

    response = await routes.retry_task("orig", TokenData("user"))
    assert response.platform == ""
    assert response.source_type == "upload"


# ── R10: LIKE escape ───────────────────────────────────────────────


def test_escape_like_basic() -> None:
    """_escape_like wraps in %...% and escapes % and _."""
    assert db._escape_like("hello") == "%hello%"
    assert db._escape_like("a_b") == "%a\\_b%"
    assert db._escape_like("a%b") == "%a\\%b%"
    assert db._escape_like("a\\b") == "%a\\\\b%"


async def test_search_with_underscore(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Search with underscore matches literally, not as wildcard."""
    await db.create_task("t1", user_id="user", message="a_b")
    await db.create_task("t2", user_id="user", message="axb")
    await db.create_task("t3", user_id="user", message="a_b_c")

    results = await db.get_user_tasks("user", search="a_b")
    ids = {r["job_id"] for r in results}
    assert "t1" in ids
    assert "t3" in ids
    assert "t2" not in ids  # underscore should NOT match 'x'


async def test_search_with_percent(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Search with percent matches literally, not as wildcard."""
    await db.create_task("t1", user_id="user", message="a%b")
    await db.create_task("t2", user_id="user", message="axb")

    results = await db.get_user_tasks("user", search="a%b")
    ids = {r["job_id"] for r in results}
    assert "t1" in ids
    assert "t2" not in ids


# ── R4: terminal task cleanup ─────────────────────────────────────


async def test_cleanup_old_terminal_tasks(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Old terminal tasks are deleted; recent and non-terminal are kept."""
    from datetime import UTC, datetime, timedelta

    old_cutoff = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    recent_cutoff = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    conn = await db._get_db()

    # Old completed task
    await db.create_task("old_complete", user_id="user")
    await conn.execute(
        "UPDATE tasks SET stage=?, created_at=? WHERE job_id=?",
        (routes.TaskStage.complete.value, old_cutoff, "old_complete"),
    )
    # Old failed task
    await db.create_task("old_failed", user_id="user")
    await conn.execute(
        "UPDATE tasks SET stage=?, created_at=? WHERE job_id=?",
        (routes.TaskStage.failed.value, old_cutoff, "old_failed"),
    )
    # Recent completed task
    await db.create_task("recent_complete", user_id="user")
    await conn.execute(
        "UPDATE tasks SET stage=?, created_at=? WHERE job_id=?",
        (routes.TaskStage.complete.value, recent_cutoff, "recent_complete"),
    )
    # Old pending task (non-terminal, should NOT be deleted)
    await db.create_task("old_pending", user_id="user")
    await conn.execute(
        "UPDATE tasks SET stage=?, created_at=? WHERE job_id=?",
        (routes.TaskStage.pending.value, old_cutoff, "old_pending"),
    )
    await conn.commit()

    deleted = await db.cleanup_old_terminal_tasks(max_age_days=30)
    assert deleted == 2

    assert await db.get_task("old_complete") is None
    assert await db.get_task("old_failed") is None
    assert await db.get_task("recent_complete") is not None
    assert await db.get_task("old_pending") is not None


async def test_cleanup_old_terminal_tasks_deletes_input_files(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cleanup_old_terminal_tasks deletes input files for old terminal tasks."""
    from datetime import UTC, datetime, timedelta

    upload_root = isolated_db
    input_file = upload_root / "old_video.mp4"
    input_file.write_bytes(b"video")

    old_cutoff = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    await db.create_task(
        "old_task",
        user_id="user",
        source_type="upload",
        input_file_path=str(input_file),
    )
    conn = await db._get_db()
    await conn.execute(
        "UPDATE tasks SET stage=?, created_at=? WHERE job_id=?",
        (routes.TaskStage.complete.value, old_cutoff, "old_task"),
    )
    await conn.commit()

    await db.cleanup_old_terminal_tasks(max_age_days=30)
    assert not input_file.exists()


# ── R5: exclude_cancelled parameter ────────────────────────────────


async def test_get_user_tasks_exclude_cancelled(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exclude_cancelled filters out cancelled tasks."""
    await db.create_task("t1", user_id="user")
    await db.create_task("t2", user_id="user")
    await db.update_progress("t2", routes.TaskStage.cancelled, 0.0, "Cancelled")

    all_tasks = await db.get_user_tasks("user", exclude_cancelled=False)
    assert len(all_tasks) == 2

    filtered = await db.get_user_tasks("user", exclude_cancelled=True)
    ids = {t["job_id"] for t in filtered}
    assert "t1" in ids
    assert "t2" not in ids

    count_all = await db.count_user_tasks("user", exclude_cancelled=False)
    assert count_all == 2
    count_filtered = await db.count_user_tasks("user", exclude_cancelled=True)
    assert count_filtered == 1


# ── R7: DB transaction lock (regression) ───────────────────────────


async def test_add_tags_to_note_with_lock(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """add_tags_to_note succeeds under the asyncio.Lock (basic smoke test)."""
    import asyncio

    await db.create_user("user", "user@example.com", "hash")

    # Ensure lock exists and is not held
    assert isinstance(db._tag_write_lock, asyncio.Lock)
    assert not db._tag_write_lock.locked()

    await db.create_task("note1", user_id="user")
    await db.create_tag("tag1", "user", "mytag", "")

    result = await db.add_tags_to_note("note1", "user", ["tag1"])
    assert result is True

    # Lock should be released after the operation
    assert not db._tag_write_lock.locked()


# ── R1: FETCHING_VIDEO_INFO progress ──────────────────────────────


async def test_process_video_url_writes_fetching_progress(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_process_video_url writes FETCHING_VIDEO_INFO before get_video_info_strict."""
    progress_calls: list[tuple] = []

    async def fake_update_progress(job_id, stage, progress, message=""):
        progress_calls.append((stage, progress, message))

    async def fake_checkpoint(job_id):
        return

    monkeypatch.setattr(routes, "update_progress", fake_update_progress)
    monkeypatch.setattr(routes, "_cancellation_checkpoint", fake_checkpoint)

    # Mock get_video_info_strict to return immediately
    call_count = [0]

    def fake_get_info(url, *, cookiefile_path=None, cancel_event=None):
        call_count[0] += 1
        return {"title": "Test", "thumbnail_url": "", "info": {"id": "test"}}

    monkeypatch.setattr(routes, "get_video_info_strict", fake_get_info)

    # Mock remaining services to avoid actual network calls
    async def fake_get_cookiefile(user_id, url):
        return None

    monkeypatch.setattr(routes, "_get_user_cookiefile", fake_get_cookiefile)

    async def fake_resolve(user_id):
        return routes.ProviderBundle(
            asr_api_key="k", asr_api_base="b", asr_model="m", asr_provider="p",
            llm_api_key="k", llm_api_base="b", llm_model="m",
        )

    monkeypatch.setattr(routes, "_resolve_providers", fake_resolve)

    # Make download_thumbnail + extract_subtitles etc. return quickly
    monkeypatch.setattr(routes, "download_thumbnail", lambda url: None)
    monkeypatch.setattr(routes, "extract_subtitles", lambda *a, **k: "")
    monkeypatch.setattr(routes, "download_audio_via_ytdlp", lambda *a, **k: "/fake")
    monkeypatch.setattr(routes, "update_task_meta", lambda *a, **k: None)

    # Short-circuit: mock _run_asr and _run_note_gen to return quickly
    async def fake_asr(*a, **k):
        return "transcript"

    async def fake_note_gen(*a, **k):
        return "# Notes"

    monkeypatch.setattr(routes, "_run_asr", fake_asr)
    monkeypatch.setattr(routes, "_run_note_gen", fake_note_gen)
    monkeypatch.setattr(routes, "transcribe_audio", lambda *a, **k: "transcript")
    monkeypatch.setattr(routes, "generate_notes", lambda *a, **k: "# Notes")

    async def fake_set_result(job_id, markdown, title=None):
        progress_calls.append(("complete_set", 1.0, "Done"))

    monkeypatch.setattr(routes, "set_result", fake_set_result)
    monkeypatch.setattr(routes, "extract_audio", lambda *a, **k: "/fake")

    import threading

    event = threading.Event()
    await routes._process_video_url("job1", "https://www.youtube.com/watch?v=test",
                                    language="en", user_id="user", cancel_event=event)

    # First progress call should be FETCHING_VIDEO_INFO
    assert len(progress_calls) > 0
    assert progress_calls[0][2] == "FETCHING_VIDEO_INFO"
    assert progress_calls[0][0] == routes.TaskStage.downloading