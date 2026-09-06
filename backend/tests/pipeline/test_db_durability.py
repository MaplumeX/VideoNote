"""DB durability tests (C4): legacy-write compatibility + race semantics.

Extracted from the legacy suites (test_core_reliability) against the new
chain's DB layer: every helper below (``update_progress``, ``set_result``) is
a legacy-column writer that still exists for compat, while the race guards
(cancel/terminal/progress) are exercised through the new conditional writers
too. The tag-transaction tests live here because they are pure DB semantics.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import pytest

from app import db
from app.schemas import TaskStage


@pytest.fixture
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    upload_dir = tmp_path / "uploads"
    database_path = upload_dir / "videonote.db"
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    await db.init_db()
    yield upload_dir
    await db.close_db()


async def test_task_migration_and_persisted_cancellation(isolated_db: Path) -> None:
    input_path = isolated_db / "source.mp4"
    input_path.write_bytes(b"video")
    await db.create_task(
        "job",
        user_id="user",
        source_type="upload",
        input_file_path=str(input_path),
    )

    task = await db.get_task("job")
    assert task is not None
    assert task["input_file_path"] == str(input_path)
    assert task["cancel_requested"] == 0
    assert task["attempt_count"] == 0

    assert await db.increment_attempt("job") is True
    assert await db.request_task_cancel("job", user_id="user") is True
    await db.set_result("job", "# must be discarded")

    cancelled = await db.get_task("job")
    assert cancelled is not None
    assert cancelled["stage"] == TaskStage.cancelled.value
    assert cancelled["status"] == "cancelled"
    assert cancelled["last_error_code"] == "TASK_CANCELLED"
    assert cancelled["cancel_requested"] == 1
    assert cancelled["attempt_count"] == 1
    assert cancelled["result_json"] is None
    assert await db.increment_attempt("job") is False
    await db.update_progress("job", TaskStage.generating_notes, 0.9, "must be ignored")
    await db.set_result("job", "# still discarded")
    guarded = await db.get_task("job")
    assert guarded is not None
    assert guarded["stage"] == TaskStage.cancelled.value
    assert guarded["message"] == "Cancelled"
    assert guarded["result_json"] is None


async def test_cancel_and_terminal_updates_are_atomic(isolated_db: Path) -> None:
    from app.pipeline.state import TaskStatus

    for index in range(8):
        job_id = f"race-{index}"
        await db.create_task(job_id, user_id="user")
        await asyncio.gather(
            db.request_task_cancel(job_id, user_id="user"),
            db.set_task_terminal(job_id, TaskStatus.complete.value, result_json="{}"),
            db.update_task_status(
                job_id, TaskStatus.running.value, phase="notegen", phase_progress=0.5
            ),
        )

        task = await db.get_task(job_id)
        assert task is not None
        if task["status"] == TaskStatus.cancelled.value:
            assert task["cancel_requested"] == 1
            assert task["result_json"] is None
            assert task["message"] == "Cancelled"
        else:
            assert task["status"] == TaskStatus.complete.value
            assert task["cancel_requested"] == 0
            assert task["result_json"] is not None


async def test_scoped_tag_write_is_atomic_and_migration_cleans_dirty_links(
    isolated_db: Path,
) -> None:
    await db.create_user("owner", "owner@example.com", "hash")
    await db.create_user("other", "other@example.com", "hash")
    await db.create_task("note", user_id="owner")
    await db.create_tag("owned", "owner", "Owned")
    await db.create_tag("foreign", "other", "Foreign")

    assert await db.add_tags_to_note("note", "owner", ["owned", "foreign"]) is False
    assert await db.get_tags_for_note("note") == []
    assert await db.add_tags_to_note("note", "owner", ["owned"]) is True
    assert [tag["id"] for tag in await db.get_tags_for_note("note")] == ["owned"]

    async with aiosqlite.connect(str(db.DB_PATH)) as connection:
        await connection.execute(
            "INSERT INTO note_tags (job_id, tag_id) VALUES (?, ?)", ("note", "foreign")
        )
        await connection.commit()

    await db.init_db()
    assert [tag["id"] for tag in await db.get_tags_for_note("note")] == ["owned"]


async def test_batch_tag_write_rejects_mixed_tasks_without_partial_links(
    isolated_db: Path,
) -> None:
    await db.create_user("owner", "owner@example.com", "hash")
    await db.create_user("other", "other@example.com", "hash")
    await db.create_task("owned-1", user_id="owner")
    await db.create_task("owned-2", user_id="owner")
    await db.create_task("foreign", user_id="other")
    await db.create_tag("tag", "owner", "Owned")
    await db.create_tag("foreign-tag", "other", "Foreign")

    assert (
        await db.batch_add_tag(["owned-1", "foreign", "owned-2"], "tag", "owner")
        is False
    )
    assert await db.get_tags_for_note("owned-1") == []
    assert await db.get_tags_for_note("owned-2") == []
    assert await db.batch_add_tag(["owned-1"], "foreign-tag", "owner") is False
    assert await db.get_tags_for_note("owned-1") == []

    assert await db.batch_add_tag(["owned-1", "owned-2"], "tag", "owner") is True
    assert [tag["id"] for tag in await db.get_tags_for_note("owned-1")] == ["tag"]
    assert [tag["id"] for tag in await db.get_tags_for_note("owned-2")] == ["tag"]
