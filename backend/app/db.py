"""SQLite database management for task storage."""

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from app.config import UPLOAD_DIR
from app.schemas import TaskStage

DB_PATH = Path(str(UPLOAD_DIR)) / "videonote.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    job_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL DEFAULT 'pending',
    progress REAL NOT NULL DEFAULT 0.0,
    message TEXT NOT NULL DEFAULT '',
    result_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db() -> None:
    """Initialize database and create tasks table."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(_CREATE_TABLE_SQL)
        await db.commit()


async def create_task(job_id: str, message: str = "Queued") -> None:
    """Create a new task record with pending status."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO tasks (job_id, stage, progress, message) VALUES (?, ?, ?, ?)",
            (job_id, TaskStage.pending.value, 0.0, message),
        )
        await db.commit()


async def get_task(job_id: str) -> dict | None:
    """Get a task record by job_id. Returns dict or None."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE job_id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


async def update_progress(
    job_id: str, stage: TaskStage, progress: float, message: str = ""
) -> None:
    """Update task progress in SQLite."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE tasks SET stage=?, progress=?, message=?, updated_at=? WHERE job_id=?",
            (stage.value, progress, message, now, job_id),
        )
        await db.commit()


async def set_result(job_id: str, markdown: str, title: str | None = None) -> None:
    """Store final note result and mark task complete."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        now = datetime.now(UTC).isoformat()
        result_json = json.dumps({"markdown": markdown, "title": title})
        await db.execute(
            "UPDATE tasks SET stage=?, progress=?, message=?, "
            "result_json=?, updated_at=? WHERE job_id=?",
            (TaskStage.complete.value, 1.0, "Done", result_json, now, job_id),
        )
        await db.commit()
