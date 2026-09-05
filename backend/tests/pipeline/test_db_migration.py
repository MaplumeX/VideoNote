"""DB migration and persistence tests for the C1 pipeline contract baseline.

Covers: legacy-schema -> migration -> backfill assertions on in-memory SQLite,
artifact read/write, and conditional writes (cancellation/terminal state wins
over progress and checkpoint writes).
"""

from pathlib import Path

import aiosqlite
import pytest

from app import db
from app.schemas import TaskStage

_LEGACY_TASKS_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    job_id TEXT PRIMARY KEY,
    user_id TEXT,
    stage TEXT NOT NULL DEFAULT 'pending',
    progress REAL NOT NULL DEFAULT 0.0,
    message TEXT NOT NULL DEFAULT '',
    result_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def _build_legacy_db(database_path: Path, rows: list[tuple[str, str]]) -> None:
    """Create a legacy-schema tasks table with the given (job_id, stage) rows."""
    async with aiosqlite.connect(str(database_path)) as connection:
        await connection.executescript(_LEGACY_TASKS_SQL)
        await connection.executemany(
            "INSERT INTO tasks (job_id, stage) VALUES (?, ?)", rows
        )
        await connection.commit()


@pytest.fixture
async def fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated file-backed DB with init_db applied (new chain only)."""
    upload_dir = tmp_path / "uploads"
    database_path = upload_dir / "videonote.db"
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    await db.init_db()
    yield database_path
    await db.close_db()


@pytest.fixture
async def legacy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Legacy-schema DB, then migrated via init_db."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    database_path = upload_dir / "videonote.db"
    rows = [
        ("legacy-pending", TaskStage.pending.value),
        ("legacy-downloading", TaskStage.downloading.value),
        ("legacy-subtitles", TaskStage.extracting_subtitles.value),
        ("legacy-transcribing", TaskStage.transcribing.value),
        ("legacy-notes", TaskStage.generating_notes.value),
        ("legacy-complete", TaskStage.complete.value),
        ("legacy-failed", TaskStage.failed.value),
        ("legacy-cancelled", TaskStage.cancelled.value),
    ]
    await _build_legacy_db(database_path, rows)
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "DB_PATH", database_path)
    await db.init_db()
    yield database_path
    await db.close_db()


class TestMigration:
    async def test_legacy_stage_backfilled_to_new_status(self, legacy_db: Path) -> None:
        expected = {
            "legacy-pending": "pending",
            "legacy-downloading": "running",
            "legacy-subtitles": "running",
            "legacy-transcribing": "running",
            "legacy-notes": "running",
            "legacy-complete": "complete",
            "legacy-failed": "failed",
            "legacy-cancelled": "cancelled",
        }
        for job_id, expected_status in expected.items():
            task = await db.get_task(job_id)
            assert task is not None, job_id
            assert task["status"] == expected_status, job_id
            # old columns untouched
            assert task["stage"] in {s.value for s in TaskStage}, job_id

    async def test_legacy_rows_have_no_checkpoint(self, legacy_db: Path) -> None:
        """A NULL checkpoint means "run from scratch" on first retry."""
        for job_id in (
            "legacy-pending", "legacy-downloading", "legacy-transcribing",
        ):
            task = await db.get_task(job_id)
            assert task is not None
            assert task["checkpoint_phase"] is None

    async def test_new_columns_exist(self, legacy_db: Path) -> None:
        task = await db.get_task("legacy-pending")
        assert task is not None
        for column in ("status", "phase", "phase_progress", "checkpoint_phase",
                       "last_error_code"):
            assert column in task

    async def test_migration_idempotent(self, legacy_db: Path) -> None:
        """Re-running init_db neither errors nor re-runs the backfill."""
        await db.close_db()
        await db.init_db()
        task = await db.get_task("legacy-downloading")
        assert task is not None
        assert task["status"] == "running"
        # legacy stage column must not be reinterpreted after re-migration
        assert task["stage"] == TaskStage.downloading.value

    async def test_backfill_does_not_touch_new_rows(
        self, fresh_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rows already carrying a status are never overwritten."""
        await db.create_task("new-row")
        new_db_conn = await aiosqlite.connect(str(fresh_db))
        await new_db_conn.execute(
            "UPDATE tasks SET status = 'running' WHERE job_id = 'new-row'"
        )
        await new_db_conn.commit()
        await new_db_conn.close()
        await db.close_db()
        await db.init_db()  # migration re-runs; backfill WHERE status IS NULL
        task = await db.get_task("new-row")
        assert task is not None
        assert task["status"] == "running"

    async def test_fresh_init_has_task_artifacts_table(self, fresh_db: Path) -> None:
        connection = await aiosqlite.connect(str(fresh_db))
        cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='task_artifacts'"
        )
        assert await cursor.fetchone() is not None
        await connection.close()


class TestArtifacts:
    async def test_save_and_get_string_artifact(self, fresh_db: Path) -> None:
        await db.create_task("job")
        await db.save_artifact("job", "transcript", "hello world")
        assert await db.get_artifact("job", "transcript") == "hello world"

    async def test_save_and_get_json_artifact(self, fresh_db: Path) -> None:
        await db.create_task("job")
        payload = {"title": "My Video", "duration": 42}
        await db.save_artifact("job", "video_meta", payload)
        assert await db.get_artifact("job", "video_meta") == payload

    async def test_upsert_overwrites(self, fresh_db: Path) -> None:
        await db.create_task("job")
        await db.save_artifact("job", "transcript", "first")
        await db.save_artifact("job", "transcript", "second")
        assert await db.get_artifact("job", "transcript") == "second"

    async def test_missing_artifact_returns_none(self, fresh_db: Path) -> None:
        await db.create_task("job")
        assert await db.get_artifact("job", "subtitle") is None
        assert await db.get_artifact("nope", "subtitle") is None


class TestCheckpoint:
    async def test_save_and_read_checkpoint(self, fresh_db: Path) -> None:
        await db.create_task("job")
        assert await db.save_checkpoint(
            "job", "subtitle", status="running", phase="audio", phase_progress=0.0
        )
        checkpoint = await db.read_checkpoint("job")
        assert checkpoint == {
            "checkpoint_phase": "subtitle",
            "attempt_count": 0,
            "status": "running",
            "cancel_requested": 0,
        }
        task = await db.get_task("job")
        assert task is not None
        assert task["phase"] == "audio"

    async def test_read_missing_task_returns_none(self, fresh_db: Path) -> None:
        assert await db.read_checkpoint("nope") is None

    async def test_no_checkpoint_means_none(self, fresh_db: Path) -> None:
        await db.create_task("job")
        checkpoint = await db.read_checkpoint("job")
        assert checkpoint is not None
        assert checkpoint["checkpoint_phase"] is None

    async def test_cancelled_wins_over_checkpoint_write(self, fresh_db: Path) -> None:
        await db.create_task("job")
        assert await db.request_task_cancel("job") is True
        assert await db.save_checkpoint("job", "audio", status="running") is False
        checkpoint = await db.read_checkpoint("job")
        assert checkpoint is not None
        assert checkpoint["checkpoint_phase"] is None

    async def test_terminal_status_blocks_checkpoint_write(self, fresh_db: Path) -> None:
        """A legacy terminal row (failed) must not be resurrected."""
        await db.create_task("job")
        connection = await aiosqlite.connect(str(fresh_db))
        await connection.execute(
            "UPDATE tasks SET status = 'failed' WHERE job_id = 'job'"
        )
        await connection.commit()
        await connection.close()
        assert await db.save_checkpoint("job", "audio") is False
        task = await db.get_task("job")
        assert task is not None
        assert task["checkpoint_phase"] is None

    async def test_legacy_terminal_stage_blocks_checkpoint_write(
        self, legacy_db: Path
    ) -> None:
        """Terminal legacy stage (status NULL) also guards the write."""
        assert await db.save_checkpoint("legacy-failed", "audio") is False
        task = await db.get_task("legacy-failed")
        assert task is not None
        assert task["checkpoint_phase"] is None

    async def test_legacy_running_row_accepts_checkpoint(
        self, legacy_db: Path
    ) -> None:
        assert await db.save_checkpoint("legacy-downloading", "audio") is True
        task = await db.get_task("legacy-downloading")
        assert task is not None
        assert task["checkpoint_phase"] == "audio"
