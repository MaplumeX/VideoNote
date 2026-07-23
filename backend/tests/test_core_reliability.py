import asyncio
from pathlib import Path

import aiosqlite
import pytest

from app import db
from app.api import routes
from app.auth import TokenData
from app.main import app
from app.schemas import TaskStage
from app.task_runner import TaskRunner


@pytest.fixture
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    upload_dir = tmp_path / "uploads"
    database_path = upload_dir / "videonote.db"
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    monkeypatch.setattr(routes, "UPLOAD_DIR", upload_dir)
    await db.init_db()
    return upload_dir


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
    for index in range(8):
        job_id = f"race-{index}"
        await db.create_task(job_id, user_id="user")
        await asyncio.gather(
            db.request_task_cancel(job_id, user_id="user"),
            db.set_result(job_id, "# result"),
            db.update_progress(job_id, TaskStage.generating_notes, 0.9, "progress"),
        )

        task = await db.get_task(job_id)
        assert task is not None
        if task["stage"] == TaskStage.cancelled.value:
            assert task["cancel_requested"] == 1
            assert task["result_json"] is None
            assert task["message"] == "Cancelled"
        else:
            assert task["stage"] == TaskStage.complete.value
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


async def test_task_runner_keeps_reference_and_prevents_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = TaskRunner()
    started = asyncio.Event()
    release = asyncio.Event()
    attempts: list[str] = []

    async def increment(job_id: str) -> bool:
        attempts.append(job_id)
        return True

    async def worker() -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr("app.task_runner.increment_attempt", increment)
    assert runner.schedule("job", worker) is True
    assert runner.schedule("job", worker) is False
    await started.wait()
    assert runner.is_running("job") is True
    release.set()
    await runner.shutdown()
    assert attempts == ["job"]


async def test_recovery_rejects_unsafe_upload_path(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outside_path = tmp_path / "outside.mp4"
    outside_path.write_bytes(b"video")
    await db.create_task(
        "unsafe",
        user_id="user",
        source_type="upload",
        input_file_path=str(outside_path),
    )

    scheduled: list[str] = []
    monkeypatch.setattr(
        routes.task_runner,
        "schedule",
        lambda job_id, factory: scheduled.append(job_id) or True,
    )
    await routes.recover_incomplete_tasks()

    task = await db.get_task("unsafe")
    assert task is not None
    assert task["stage"] == TaskStage.failed.value
    assert task["message"] == "TASK_RECOVERY_INPUT_INVALID"
    assert scheduled == []


async def test_recovery_schedules_valid_url_and_upload(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = isolated_db / "source.mp4"
    source.write_bytes(b"video")
    await db.create_task(
        "url",
        user_id="user",
        source_type="url",
        video_url="https://www.youtube.com/watch?v=abcdefghijk",
        language="zh-CN",
    )
    await db.create_task(
        "upload",
        user_id="user",
        source_type="upload",
        input_file_path=str(source),
        language="en",
    )

    scheduled: list[str] = []
    monkeypatch.setattr(
        routes.task_runner,
        "schedule",
        lambda job_id, factory: scheduled.append(job_id) or True,
    )
    await routes.recover_incomplete_tasks()

    assert scheduled == ["url", "upload"]


async def test_recovery_uses_stable_code_for_unsupported_url(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await db.create_task(
        "unsupported",
        user_id="user",
        source_type="url",
        video_url="https://example.com/video",
    )
    monkeypatch.setattr(
        routes.task_runner,
        "schedule",
        lambda job_id, factory: pytest.fail("unsupported URL must not be scheduled"),
    )

    await routes.recover_incomplete_tasks()

    task = await db.get_task("unsupported")
    assert task is not None
    assert task["stage"] == TaskStage.failed.value
    assert task["message"] == "TASK_RECOVERY_UNSUPPORTED_URL"


async def test_cancel_checkpoint_blocks_later_file_stages(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = isolated_db / "source.mp4"
    source.write_bytes(b"video")
    await db.create_task(
        "job",
        user_id="user",
        source_type="upload",
        input_file_path=str(source),
    )
    calls: list[str] = []

    async def fake_to_thread(function, *args, **kwargs):
        calls.append(function.__name__)
        if function is routes.extract_audio:
            await db.request_task_cancel("job", user_id="user")
            return None
        raise AssertionError("cancelled task entered a later processing stage")

    monkeypatch.setattr(routes.asyncio, "to_thread", fake_to_thread)
    with pytest.raises(asyncio.CancelledError):
        await routes._process_video_file("job", str(source), user_id="user")

    task = await db.get_task("job")
    assert task is not None
    assert task["stage"] == TaskStage.cancelled.value
    assert calls == ["extract_audio"]
    assert not source.exists()


async def test_delete_running_task_waits_for_runner_and_removes_input(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = isolated_db / "source.mp4"
    source.write_bytes(b"video")
    await db.create_task(
        "job",
        user_id="user",
        source_type="upload",
        input_file_path=str(source),
    )
    cancelled: list[str] = []

    async def cancel_and_wait(job_id: str) -> bool:
        cancelled.append(job_id)
        return True

    monkeypatch.setattr(routes.task_runner, "cancel_and_wait", cancel_and_wait)
    response = await routes.cancel_or_delete_task("job", TokenData("user"))

    assert response == {"detail": "Task deleted"}
    assert cancelled == ["job"]
    assert await db.get_task("job") is None
    assert not source.exists()


def test_upload_language_is_a_multipart_form_field() -> None:
    operation = app.openapi()["paths"]["/api/upload"]["post"]
    assert "requestBody" in operation
    assert "multipart/form-data" in operation["requestBody"]["content"]
    assert all(parameter["name"] != "language" for parameter in operation.get("parameters", []))
