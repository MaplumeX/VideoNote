"""SQLite database management for task storage."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from app.config import UPLOAD_DIR
from app.schemas import TaskStage

DB_PATH = Path(str(UPLOAD_DIR)) / "videonote.db"

_CREATE_TABLE_SQL = """
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

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

CREATE TABLE IF NOT EXISTS user_providers (
    user_id TEXT NOT NULL,
    category TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    api_key_encrypted TEXT NOT NULL DEFAULT '',
    api_base TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, category),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


async def init_db() -> None:
    """Initialize database and create all tables."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        # Add user_id column to tasks if it doesn't exist (migration)
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN user_id TEXT REFERENCES users(id)")
        except aiosqlite.OperationalError:
            pass  # Column already exists
        # Add metadata columns to tasks
        for col_def in [
            "ALTER TABLE tasks ADD COLUMN video_url TEXT",
            "ALTER TABLE tasks ADD COLUMN file_name TEXT",
            "ALTER TABLE tasks ADD COLUMN platform TEXT",
            "ALTER TABLE tasks ADD COLUMN language TEXT",
            "ALTER TABLE tasks ADD COLUMN source_type TEXT",
        ]:
            try:
                await db.execute(col_def)
            except aiosqlite.OperationalError:
                pass
        await db.executescript(_CREATE_TABLE_SQL)
        await db.commit()
    await _cleanup_expired_tokens()


async def create_task(
    job_id: str,
    message: str = "Queued",
    user_id: str | None = None,
    *,
    video_url: str | None = None,
    file_name: str | None = None,
    platform: str | None = None,
    language: str | None = None,
    source_type: str | None = None,
) -> None:
    """Create a new task record with pending status."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO tasks (job_id, user_id, stage, progress, message, "
            "video_url, file_name, platform, language, source_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, user_id, TaskStage.pending.value, 0.0, message,
             video_url, file_name, platform, language, source_type),
        )
        await db.commit()


async def get_task(job_id: str) -> dict | None:
    """Get a task record by job_id. Returns dict or None."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks WHERE job_id = ?", (job_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


async def get_user_tasks(user_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
    """Get tasks for a user with pagination, newest first."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT job_id, stage, progress, message, created_at, updated_at, "
            "video_url, file_name, platform, language, source_type "
            "FROM tasks WHERE user_id = ? ORDER BY created_at DESC "
            "LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def count_user_tasks(user_id: str) -> int:
    """Count total tasks for a user."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row[0]


async def delete_task(job_id: str, user_id: str | None = None) -> bool:
    """Delete a task record. Returns True if deleted, False if not found."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        if user_id:
            cursor = await db.execute(
                "DELETE FROM tasks WHERE job_id = ? AND user_id = ?", (job_id, user_id)
            )
        else:
            cursor = await db.execute("DELETE FROM tasks WHERE job_id = ?", (job_id,))
        await db.commit()
        return cursor.rowcount > 0


async def update_progress(
    job_id: str, stage: TaskStage, progress: float, message: str = ""
) -> None:
    """Update task progress in SQLite. Skips if task is already in a terminal state."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT stage FROM tasks WHERE job_id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        if row and row["stage"] in (
            TaskStage.complete.value,
            TaskStage.failed.value,
            TaskStage.cancelled.value,
        ):
            return  # Already in terminal state, skip update
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE tasks SET stage=?, progress=?, message=?, updated_at=? WHERE job_id=?",
            (stage.value, progress, message, now, job_id),
        )
        await db.commit()


async def set_result(job_id: str, markdown: str, title: str | None = None) -> None:
    """Store final note result and mark task complete. Skips if task is cancelled."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT stage FROM tasks WHERE job_id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        if row and row["stage"] == TaskStage.cancelled.value:
            return  # Task was cancelled, discard result
        now = datetime.now(UTC).isoformat()
        result_json = json.dumps({"markdown": markdown, "title": title})
        await db.execute(
            "UPDATE tasks SET stage=?, progress=?, message=?, "
            "result_json=?, updated_at=? WHERE job_id=?",
            (TaskStage.complete.value, 1.0, "Done", result_json, now, job_id),
        )
        await db.commit()


# --- User operations ---


async def create_user(user_id: str, email: str, password_hash: str) -> None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (user_id, email, password_hash),
        )
        await db.commit()


async def get_user_by_email(email: str) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


async def get_user_by_id(user_id: str) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


# --- Refresh token operations ---


async def create_refresh_token(
    token_id: str, user_id: str, token_hash: str, expires_at: str
) -> None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at) VALUES (?, ?, ?, ?)",
            (token_id, user_id, token_hash, expires_at),
        )
        await db.commit()


async def get_refresh_token_by_hash(token_hash: str) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM refresh_tokens WHERE token_hash = ?", (token_hash,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


async def revoke_refresh_token(token_hash: str) -> bool:
    """Revoke a refresh token. Returns True if revoked, False if already revoked."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        now = datetime.now(UTC).isoformat()
        cursor = await db.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (now, token_hash),
        )
        await db.commit()
        return cursor.rowcount > 0


async def revoke_all_user_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a user (reuse detection)."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (now, user_id),
        )
        await db.commit()


async def _cleanup_expired_tokens() -> None:
    """Delete refresh tokens that expired more than 30 days ago."""
    cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM refresh_tokens WHERE expires_at < ?", (cutoff,))
        await db.commit()


# --- Provider config operations ---


async def save_provider_config(
    user_id: str,
    category: str,
    provider: str,
    model: str,
    api_key_encrypted: str,
    api_base: str,
) -> None:
    """UPSERT a user's provider config for a given category (asr/llm)."""
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO user_providers (user_id, category, provider, model, "
            "api_key_encrypted, api_base, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, category) DO UPDATE SET "
            "provider=excluded.provider, model=excluded.model, "
            "api_key_encrypted=excluded.api_key_encrypted, "
            "api_base=excluded.api_base, updated_at=excluded.updated_at",
            (user_id, category, provider, model, api_key_encrypted, api_base, now),
        )
        await db.commit()


async def get_provider_config(user_id: str, category: str) -> dict | None:
    """Get a user's provider config for a given category. Returns dict or None."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM user_providers WHERE user_id = ? AND category = ?",
            (user_id, category),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


async def get_all_provider_configs(user_id: str) -> dict:
    """Get all provider configs for a user. Returns {"asr": {...}, "llm": {...}}."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM user_providers WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        result: dict = {}
        for row in rows:
            result[row["category"]] = dict(row)
        return result
