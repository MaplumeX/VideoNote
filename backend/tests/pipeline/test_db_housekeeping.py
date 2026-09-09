"""DB housekeeping + query-semantics tests (C4), extracted from the legacy suites.

Covers: terminal-task cleanup (age cutoff, input-file removal), the
exclude_cancelled filter, LIKE escaping in search, the LIKE/underscore and
percent wildcard cases, and note-content title sync (update_note_content).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app import db
from app.pipeline.state import TaskStatus


@pytest.fixture
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    upload_dir = tmp_path / "uploads"
    database_path = upload_dir / "videonote.db"
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    await db.init_db()
    yield upload_dir
    await db.close_db()


async def _age_task(job_id: str, *, status: TaskStatus, days: int) -> None:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    conn = await db._get_db()
    # created_at is written by SQLite CURRENT_TIMESTAMP ("YYYY-MM-DD HH:MM:SS");
    # use the same format so the string comparison in cleanup matches.
    sqlite_ts = cutoff.replace("T", " ").split(".")[0]
    await conn.execute(
        "UPDATE tasks SET status=?, stage=?, created_at=? WHERE job_id=?",
        (status.value, status.value, sqlite_ts, job_id),
    )
    await conn.commit()


async def test_cleanup_old_terminal_tasks(isolated_db: Path) -> None:
    """Old terminal tasks are deleted; recent and non-terminal are kept."""
    for job_id, status in [
        ("old_complete", TaskStatus.complete),
        ("old_failed", TaskStatus.failed),
        ("recent_complete", TaskStatus.complete),
        ("old_pending", TaskStatus.pending),
    ]:
        await db.create_task(job_id, user_id="user")
        await _age_task(job_id, status=status, days=31 if "old" in job_id else 1)

    deleted = await db.cleanup_old_terminal_tasks(max_age_days=30)
    assert deleted == 2

    assert await db.get_task("old_complete") is None
    assert await db.get_task("old_failed") is None
    assert await db.get_task("recent_complete") is not None
    assert await db.get_task("old_pending") is not None


async def test_cleanup_old_terminal_tasks_deletes_input_files(
    isolated_db: Path,
) -> None:
    input_file = isolated_db / "old_video.mp4"
    input_file.write_bytes(b"video")
    await db.create_task(
        "old_task", user_id="user", source_type="upload",
        input_file_path=str(input_file),
    )
    await _age_task("old_task", status=TaskStatus.complete, days=31)

    await db.cleanup_old_terminal_tasks(max_age_days=30)
    assert not input_file.exists()

async def test_cleanup_failed_task_files_removes_input_and_wav(
    isolated_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The delayed housekeeping removes both retained file classes of an
    aged failed task: the upload input and the per-job WAV."""
    input_file = isolated_db / "failed_in.mp4"
    input_file.write_bytes(b"video")
    await db.create_task(
        "failed_task", user_id="user", source_type="upload",
        input_file_path=str(input_file),
    )
    await _age_task("failed_task", status=TaskStatus.failed, days=8)

    # The per-job WAV lives under tempfile.gettempdir(); point it at the
    # test's tmp area so the test neither touches nor depends on the real
    # temp dir (both db and the pipeline resolve the same base).
    fake_tmp = tmp_path / "wavtmp"
    fake_tmp.mkdir()
    import tempfile
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(fake_tmp))
    wav_dir = fake_tmp / "videonote_pipeline_audio"
    wav_dir.mkdir()
    wav = wav_dir / "failed_task.wav"
    wav.write_bytes(b"RIFF....")

    cleaned = await db.cleanup_failed_task_files(max_age_days=7)
    assert cleaned == 1
    assert not input_file.exists()
    assert not wav.exists()
    task = await db.get_task("failed_task")
    assert task["input_file_path"] is None

async def test_cleanup_failed_task_files_keeps_recent_failed_tasks(
    isolated_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed task inside the retention window keeps its files — they are
    the retry-resume inputs."""
    input_file = isolated_db / "recent_in.mp4"
    input_file.write_bytes(b"video")
    await db.create_task(
        "recent_failed", user_id="user", source_type="upload",
        input_file_path=str(input_file),
    )
    await _age_task("recent_failed", status=TaskStatus.failed, days=1)

    cleaned = await db.cleanup_failed_task_files(max_age_days=7)
    assert cleaned == 0
    assert input_file.exists()
    task = await db.get_task("recent_failed")
    assert task["input_file_path"] == str(input_file)


async def test_get_user_tasks_exclude_cancelled(isolated_db: Path) -> None:
    await db.create_task("t1", user_id="user")
    await db.create_task("t2", user_id="user")
    await db.request_task_cancel("t2", user_id="user")

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


async def test_add_tags_to_note_with_lock(isolated_db: Path) -> None:
    import asyncio

    await db.create_user("user", "user@example.com", "hash")
    assert isinstance(db._tag_write_lock, asyncio.Lock)
    assert not db._tag_write_lock.locked()

    await db.create_task("note1", user_id="user")
    await db.create_tag("tag1", "user", "mytag", "")
    assert await db.add_tags_to_note("note1", "user", ["tag1"]) is True
    assert not db._tag_write_lock.locked()


def test_escape_like_basic() -> None:
    escaped = db._escape_like("a_b%c")
    assert escaped == "%a\\_b\\%c%"


async def test_search_with_underscore(isolated_db: Path) -> None:
    await db.create_task("u1", user_id="user", file_name="file_one.mp4")
    await db.create_task("u2", user_id="user", file_name="fileXone.mp4")
    results = await db.get_user_tasks("user", search="file_one")
    assert [t["job_id"] for t in results] == ["u1"]


async def test_search_with_percent(isolated_db: Path) -> None:
    await db.create_task("p1", user_id="user", file_name="50off.mp4")
    await db.create_task("p2", user_id="user", file_name="5Xoff.mp4")
    results = await db.get_user_tasks("user", search="50off")
    assert [t["job_id"] for t in results] == ["p1"]


async def test_find_active_task_by_url_returns_active_task(isolated_db: Path) -> None:
    url = "https://www.youtube.com/watch?v=abcdefghijk"
    await db.create_task("job-1", user_id="user", video_url=url,
                         platform="youtube", source_type="url")
    await db.create_task("job-2", user_id="user", video_url=url,
                         platform="youtube", source_type="url")
    await db.set_task_terminal("job-2", TaskStatus.complete.value, result_json="{}")
    await db.create_task("job-3", user_id="user", video_url=url,
                         platform="youtube", source_type="url")
    await db.request_task_cancel("job-3", user_id="user")

    found = await db.find_active_task_by_url("user", url)
    assert found is not None
    assert found["job_id"] == "job-1"
    assert await db.find_active_task_by_url("other", url) is None
    assert await db.find_active_task_by_url("user", "https://other.com") is None


async def test_list_tasks_null_status_displays_via_legacy_mapping(
    isolated_db: Path,
) -> None:
    """A new-chain row created before its first status write (status NULL)
    must display as pending, not crash the TaskListItem model (500)."""
    from app.schemas import TaskListItem

    await db.create_task("fresh", user_id="user", video_url="https://x",
                         platform="youtube", source_type="url")
    row = await db.get_task("fresh")
    assert row["status"] is None  # the window the COALESCE guards

    tasks = await db.get_user_tasks("user")
    assert tasks[0]["status"] == "pending"
    TaskListItem(**tasks[0])  # must not raise

    # Terminal legacy rows map through unchanged.
    await db.create_task("old", user_id="user")
    conn = await db._get_db()
    await conn.execute("UPDATE tasks SET stage = 'complete' WHERE job_id = 'old'")
    await conn.commit()
    tasks = await db.get_user_tasks("user")
    by_id = {t["job_id"]: t["status"] for t in tasks}
    assert by_id["old"] == "complete"


async def test_update_note_content_syncs_title_column(isolated_db: Path) -> None:
    import json

    await db.create_user("user-b", "user-b@example.com", "hash")
    await db.create_task("job-b", user_id="user-b", title="Video Title")
    await db.set_task_terminal(
        "job-b", TaskStatus.complete.value,
        result_json=json.dumps({"markdown": "initial", "title": "Video Title"}),
    )

    assert await db.update_note_content("job-b", "new markdown", title="新标题")
    task = await db.get_task("job-b")
    assert task is not None
    assert task["title"] == "新标题"
    result = json.loads(task["result_json"])
    assert result["title"] == "新标题"
    assert result["markdown"] == "new markdown"


async def test_update_note_content_preserves_title_when_none(isolated_db: Path) -> None:
    import json

    await db.create_user("user-c", "user-c@example.com", "hash")
    await db.create_task("job-c", user_id="user-c", title="Original Title")
    await db.set_task_terminal(
        "job-c", TaskStatus.complete.value,
        result_json=json.dumps({"markdown": "initial", "title": "Original Title"}),
    )

    await db.update_note_content("job-c", "edited markdown", title=None)
    task = await db.get_task("job-c")
    assert task is not None
    assert task["title"] == "Original Title"
    result = json.loads(task["result_json"])
    assert result["title"] == "Original Title"
