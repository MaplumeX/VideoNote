"""SQLite database management for task storage."""

import json
import uuid
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

CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_tags_user_id ON tags(user_id);

CREATE TABLE IF NOT EXISTS folders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    parent_id TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES folders(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_folders_user_id ON folders(user_id);
CREATE INDEX IF NOT EXISTS idx_folders_parent_id ON folders(parent_id);

CREATE TABLE IF NOT EXISTS note_tags (
    job_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, tag_id),
    FOREIGN KEY (job_id) REFERENCES tasks(job_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


async def _get_db() -> aiosqlite.Connection:
    """Open a database connection with foreign keys enabled and row factory set."""
    db = await aiosqlite.connect(str(DB_PATH))
    await db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    """Initialize database and create all tables."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    db = await _get_db()
    try:
        await db.execute("PRAGMA journal_mode=WAL")
        # Create all tables first (including new tags, folders, note_tags, schema_version)
        await db.executescript(_CREATE_TABLE_SQL)
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
        # Add organization columns to tasks
        for col_def in [
            "ALTER TABLE tasks ADD COLUMN folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL",
            "ALTER TABLE tasks ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN favorited_at TEXT",
        ]:
            try:
                await db.execute(col_def)
            except aiosqlite.OperationalError:
                pass
        # Add indexes for new columns
        await db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_tasks_folder_id ON tasks(folder_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_is_favorite ON tasks(is_favorite);
        """)
        await db.commit()
    finally:
        await db.close()
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
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO tasks (job_id, user_id, stage, progress, message, "
            "video_url, file_name, platform, language, source_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, user_id, TaskStage.pending.value, 0.0, message,
             video_url, file_name, platform, language, source_type),
        )
        await db.commit()
    finally:
        await db.close()


async def get_task(job_id: str) -> dict | None:
    """Get a task record by job_id. Returns dict or None."""
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM tasks WHERE job_id = ?", (job_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


async def get_user_tasks(
    user_id: str,
    limit: int = 20,
    offset: int = 0,
    *,
    folder_id: str | None = None,
    tag_id: str | None = None,
    is_favorite: bool | None = None,
    folder_null: bool = False,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> list[dict]:
    """Get tasks for a user with pagination and optional filters, newest first."""
    db = await _get_db()
    try:
        query = (
            "SELECT t.job_id, t.stage, t.progress, t.message, t.created_at, t.updated_at, "
            "t.video_url, t.file_name, t.platform, t.language, t.source_type, t.result_json, "
            "t.folder_id, t.is_favorite, t.favorited_at "
            "FROM tasks t"
        )
        params: list = []
        joins = ""
        conditions = ["t.user_id = ?"]
        params.append(user_id)

        if tag_id is not None:
            joins += " JOIN note_tags nt ON t.job_id = nt.job_id"
            conditions.append("nt.tag_id = ?")
            params.append(tag_id)

        if folder_id is not None:
            conditions.append("t.folder_id = ?")
            params.append(folder_id)

        if folder_null:
            conditions.append("t.folder_id IS NULL")

        if is_favorite is not None:
            conditions.append("t.is_favorite = ?")
            params.append(1 if is_favorite else 0)

        if search is not None:
            conditions.append(
                "(t.message LIKE ? OR t.video_url LIKE ? OR t.file_name LIKE ? "
                "OR json_extract(t.result_json, '$.title') LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like])

        allowed_sort = {"created_at", "title", "stage"}
        if sort_by == "title":
            # title in result_json JSON; sort by extracted title,
            # fallback to empty string for NULLs
            sort_expr = "COALESCE(json_extract(t.result_json, '$.title'), '')"

        elif sort_by in allowed_sort:
            sort_expr = f"t.{sort_by}"
        else:
            sort_expr = "t.created_at"
        order_dir = "ASC" if sort_order.lower() == "asc" else "DESC"

        where = " AND ".join(conditions)
        query = f"{query}{joins} WHERE {where} ORDER BY {sort_expr} {order_dir} LIMIT ? OFFSET ?"

        if tag_id is not None:
            query = f"SELECT DISTINCT * FROM ({query})"

        params.extend([limit, offset])
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            # Extract title from result_json if available
            title = None
            if d.get("result_json"):
                try:
                    parsed = json.loads(d["result_json"])
                    title = parsed.get("title")
                except (json.JSONDecodeError, TypeError):
                    pass
            d["title"] = title
            del d["result_json"]  # Don't return full result_json in list API
            result.append(d)
        return result
    finally:
        await db.close()


async def count_user_tasks(
    user_id: str,
    *,
    folder_id: str | None = None,
    tag_id: str | None = None,
    is_favorite: bool | None = None,
    folder_null: bool = False,
    search: str | None = None,
) -> int:
    """Count total tasks for a user with optional filters."""
    db = await _get_db()
    try:
        query = "SELECT COUNT(DISTINCT t.job_id) FROM tasks t"
        params: list = []
        joins = ""
        conditions = ["t.user_id = ?"]
        params.append(user_id)

        if tag_id is not None:
            joins += " JOIN note_tags nt ON t.job_id = nt.job_id"
            conditions.append("nt.tag_id = ?")
            params.append(tag_id)

        if folder_id is not None:
            conditions.append("t.folder_id = ?")
            params.append(folder_id)

        if folder_null:
            conditions.append("t.folder_id IS NULL")

        if is_favorite is not None:
            conditions.append("t.is_favorite = ?")
            params.append(1 if is_favorite else 0)

        if search is not None:
            conditions.append(
                "(t.message LIKE ? OR t.video_url LIKE ? OR t.file_name LIKE ? "
                "OR json_extract(t.result_json, '$.title') LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like])

        where = " AND ".join(conditions)
        query = f"{query}{joins} WHERE {where}"
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        return row[0]  # type: ignore[index]
    finally:
        await db.close()


async def delete_task(job_id: str, user_id: str | None = None) -> bool:
    """Delete a task record. Returns True if deleted, False if not found."""
    db = await _get_db()
    try:
        if user_id:
            cursor = await db.execute(
                "DELETE FROM tasks WHERE job_id = ? AND user_id = ?", (job_id, user_id)
            )
        else:
            cursor = await db.execute("DELETE FROM tasks WHERE job_id = ?", (job_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def update_progress(
    job_id: str, stage: TaskStage, progress: float, message: str = ""
) -> None:
    """Update task progress in SQLite. Skips if task is already in a terminal state."""
    db = await _get_db()
    try:
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
    finally:
        await db.close()


async def set_result(job_id: str, markdown: str, title: str | None = None) -> None:
    """Store final note result and mark task complete. Skips if task is cancelled."""
    db = await _get_db()
    try:
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
    finally:
        await db.close()


# --- User operations ---


async def create_user(user_id: str, email: str, password_hash: str) -> None:
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (user_id, email, password_hash),
        )
        await db.commit()
    finally:
        await db.close()


async def get_user_by_email(email: str) -> dict | None:
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


async def get_user_by_id(user_id: str) -> dict | None:
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


# --- Refresh token operations ---


async def create_refresh_token(
    token_id: str, user_id: str, token_hash: str, expires_at: str
) -> None:
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at) VALUES (?, ?, ?, ?)",
            (token_id, user_id, token_hash, expires_at),
        )
        await db.commit()
    finally:
        await db.close()


async def get_refresh_token_by_hash(token_hash: str) -> dict | None:
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM refresh_tokens WHERE token_hash = ?", (token_hash,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


async def revoke_refresh_token(token_hash: str) -> bool:
    """Revoke a refresh token. Returns True if revoked, False if already revoked."""
    db = await _get_db()
    try:
        now = datetime.now(UTC).isoformat()
        cursor = await db.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (now, token_hash),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def revoke_all_user_tokens(user_id: str) -> None:
    """Revoke all refresh tokens for a user (reuse detection)."""
    db = await _get_db()
    try:
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (now, user_id),
        )
        await db.commit()
    finally:
        await db.close()


async def _cleanup_expired_tokens() -> None:
    """Delete refresh tokens that expired more than 30 days ago."""
    cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    db = await _get_db()
    try:
        await db.execute("DELETE FROM refresh_tokens WHERE expires_at < ?", (cutoff,))
        await db.commit()
    finally:
        await db.close()


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
    db = await _get_db()
    try:
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
    finally:
        await db.close()


async def get_provider_config(user_id: str, category: str) -> dict | None:
    """Get a user's provider config for a given category. Returns dict or None."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM user_providers WHERE user_id = ? AND category = ?",
            (user_id, category),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


async def get_all_provider_configs(user_id: str) -> dict:
    """Get all provider configs for a user. Returns {"asr": {...}, "llm": {...}}."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM user_providers WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        result: dict = {}
        for row in rows:
            result[row["category"]] = dict(row)
        return result
    finally:
        await db.close()


# --- Tag operations ---


async def create_tag(tag_id: str, user_id: str, name: str, color: str = "") -> dict:
    """Create a new tag for a user. Returns the created tag dict."""
    now = datetime.now(UTC).isoformat()
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO tags (id, user_id, name, color, created_at) VALUES (?, ?, ?, ?, ?)",
            (tag_id, user_id, name, color, now),
        )
        await db.commit()
        return {"id": tag_id, "user_id": user_id, "name": name, "color": color, "created_at": now}
    finally:
        await db.close()


async def get_tags_by_user(user_id: str) -> list[dict]:
    """Get all tags for a user with note counts."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT t.id, t.user_id, t.name, t.color, t.created_at, "
            "COUNT(nt.job_id) AS note_count "
            "FROM tags t LEFT JOIN note_tags nt ON t.id = nt.tag_id "
            "WHERE t.user_id = ? "
            "GROUP BY t.id ORDER BY t.name",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_tag_by_id(tag_id: str) -> dict | None:
    """Get a tag by ID. Returns dict or None."""
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM tags WHERE id = ?", (tag_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


async def update_tag(tag_id: str, name: str | None = None, color: str | None = None) -> dict | None:
    """Update a tag's name and/or color. Returns updated dict or None if not found."""
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM tags WHERE id = ?", (tag_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        new_name = name if name is not None else row["name"]
        new_color = color if color is not None else row["color"]
        await db.execute(
            "UPDATE tags SET name = ?, color = ? WHERE id = ?",
            (new_name, new_color, tag_id),
        )
        await db.commit()
        return {"id": tag_id, "user_id": row["user_id"], "name": new_name, "color": new_color,
                "created_at": row["created_at"]}
    finally:
        await db.close()


async def delete_tag(tag_id: str) -> bool:
    """Delete a tag. CASCADE removes note_tags associations. Returns True if deleted."""
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def get_or_create_tag_by_name(user_id: str, name: str, color: str = "") -> dict:
    """Get an existing tag by name for user, or create it. Returns the tag dict."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM tags WHERE user_id = ? AND name = ?",
            (user_id, name),
        )
        row = await cursor.fetchone()
        if row is not None:
            return dict(row)
        # Create new tag
        tag_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        await db.execute(
            "INSERT INTO tags (id, user_id, name, color, created_at) VALUES (?, ?, ?, ?, ?)",
            (tag_id, user_id, name, color, now),
        )
        await db.commit()
        return {"id": tag_id, "user_id": user_id, "name": name, "color": color, "created_at": now}
    finally:
        await db.close()


# --- Folder operations ---


async def create_folder(
    folder_id: str, user_id: str, name: str, parent_id: str | None = None,
    sort_order: int = 0,
) -> dict:
    """Create a new folder. Returns the created folder dict."""
    now = datetime.now(UTC).isoformat()
    db = await _get_db()
    try:
        await db.execute(
            "INSERT INTO folders "
            "(id, user_id, name, parent_id, sort_order, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (folder_id, user_id, name, parent_id, sort_order, now, now),
        )
        await db.commit()
        return {"id": folder_id, "user_id": user_id, "name": name,
                "parent_id": parent_id, "sort_order": sort_order,
                "created_at": now, "updated_at": now}
    finally:
        await db.close()


async def get_folders_by_user(user_id: str) -> list[dict]:
    """Get all folders for a user as a flat list."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM folders WHERE user_id = ? ORDER BY sort_order, name",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_folder_tree(user_id: str) -> list[dict]:
    """Get folder tree with note counts. Returns nested list."""
    db = await _get_db()
    try:
        # Get all folders
        cursor = await db.execute(
            "SELECT * FROM folders WHERE user_id = ? ORDER BY sort_order, name",
            (user_id,),
        )
        folders = [dict(row) for row in await cursor.fetchall()]

        # Get note counts per folder
        cursor = await db.execute(
            "SELECT folder_id, COUNT(*) as note_count FROM tasks "
            "WHERE user_id = ? AND folder_id IS NOT NULL "
            "GROUP BY folder_id",
            (user_id,),
        )
        count_map: dict[str, int] = {}
        for row in await cursor.fetchall():
            count_map[row["folder_id"]] = row["note_count"]

        # Build tree
        folder_map: dict[str, dict] = {}
        for f in folders:
            f["note_count"] = count_map.get(f["id"], 0)
            f["children"] = []
            folder_map[f["id"]] = f

        roots: list[dict] = []
        for f in folders:
            if f["parent_id"] and f["parent_id"] in folder_map:
                folder_map[f["parent_id"]]["children"].append(f)
            else:
                roots.append(f)
        return roots
    finally:
        await db.close()


async def get_folder_by_id(folder_id: str) -> dict | None:
    """Get a folder by ID. Returns dict or None."""
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


async def _would_create_cycle(db: aiosqlite.Connection, folder_id: str, new_parent_id: str) -> bool:
    """Walk up from new_parent_id; if we reach folder_id, it's a cycle."""
    current = new_parent_id
    while current:
        if current == folder_id:
            return True
        cursor = await db.execute("SELECT parent_id FROM folders WHERE id = ?", (current,))
        row = await cursor.fetchone()
        current = row["parent_id"] if row else None  # type: ignore[index,assignment]
    return False


async def update_folder(
    folder_id: str, name: str | None = None, parent_id: str | None = None,
) -> dict | None:
    """Update a folder's name and/or parent. Returns updated dict or None if not found.
    Pass parent_id="" to move folder to root level.
    """
    db = await _get_db()
    try:
        cursor = await db.execute("SELECT * FROM folders WHERE id = ?", (folder_id,))
        row = await cursor.fetchone()
        if row is None:
            return None

        new_name = name if name is not None else row["name"]

        # Handle parent_id update
        if parent_id is not None:
            # Check for cycle if moving to a new parent
            if parent_id and await _would_create_cycle(db, folder_id, parent_id):
                raise ValueError("Moving folder would create a cycle")
            new_parent_id: str | None = parent_id if parent_id else None
        else:
            new_parent_id = row["parent_id"]

        now = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE folders SET name = ?, parent_id = ?, updated_at = ? WHERE id = ?",
            (new_name, new_parent_id, now, folder_id),
        )
        await db.commit()
        return {"id": folder_id, "user_id": row["user_id"], "name": new_name,
                "parent_id": new_parent_id, "sort_order": row["sort_order"],
                "created_at": row["created_at"], "updated_at": now}
    finally:
        await db.close()


async def delete_folder(folder_id: str) -> bool:
    """Delete a folder. CASCADE deletes subfolders; notes become uncategorized."""
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# --- Note-Tag operations ---


async def add_tags_to_note(job_id: str, tag_ids: list[str]) -> None:
    """Add tags to a note. Ignores duplicates via INSERT OR IGNORE."""
    now = datetime.now(UTC).isoformat()
    db = await _get_db()
    try:
        for tag_id in tag_ids:
            await db.execute(
                "INSERT OR IGNORE INTO note_tags (job_id, tag_id, created_at) VALUES (?, ?, ?)",
                (job_id, tag_id, now),
            )
        await db.commit()
    finally:
        await db.close()


async def remove_tag_from_note(job_id: str, tag_id: str) -> bool:
    """Remove a tag from a note. Returns True if removed."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM note_tags WHERE job_id = ? AND tag_id = ?",
            (job_id, tag_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def get_tags_for_note(job_id: str) -> list[dict]:
    """Get all tags associated with a note."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT t.id, t.user_id, t.name, t.color, t.created_at "
            "FROM tags t JOIN note_tags nt ON t.id = nt.tag_id "
            "WHERE nt.job_id = ? ORDER BY t.name",
            (job_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


# --- Note folder/favorite operations ---


async def move_note_to_folder(job_id: str, folder_id: str | None) -> bool:
    """Move a note to a folder (or uncategorized if folder_id is None). Returns True if updated."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "UPDATE tasks SET folder_id = ? WHERE job_id = ?",
            (folder_id, job_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def toggle_favorite(job_id: str, is_favorite: bool) -> bool:
    """Set or unset favorite on a note. Returns True if updated."""
    now = datetime.now(UTC).isoformat()
    db = await _get_db()
    try:
        favorited_at = now if is_favorite else None
        cursor = await db.execute(
            "UPDATE tasks SET is_favorite = ?, favorited_at = ?, updated_at = ? WHERE job_id = ?",
            (1 if is_favorite else 0, favorited_at, now, job_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def update_note_content(job_id: str, markdown: str, title: str | None = None) -> bool:
    """Update the markdown content of a note. Returns True if updated."""
    db = await _get_db()
    try:
        # Read existing result_json to preserve/merge title
        cursor = await db.execute("SELECT result_json FROM tasks WHERE job_id = ?", (job_id,))
        row = await cursor.fetchone()
        existing_title = None
        if row and row["result_json"]:
            try:
                parsed = json.loads(row["result_json"])
                existing_title = parsed.get("title")
            except (json.JSONDecodeError, TypeError):
                pass

        final_title = title if title is not None else existing_title
        now = datetime.now(UTC).isoformat()
        result_json = json.dumps({"markdown": markdown, "title": final_title})
        cursor = await db.execute(
            "UPDATE tasks SET result_json = ?, updated_at = ? WHERE job_id = ?",
            (result_json, now, job_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# --- Batch operations ---


async def batch_add_tag(job_ids: list[str], tag_id: str) -> None:
    """Add a tag to multiple notes."""
    now = datetime.now(UTC).isoformat()
    db = await _get_db()
    try:
        for job_id in job_ids:
            await db.execute(
                "INSERT OR IGNORE INTO note_tags (job_id, tag_id, created_at) VALUES (?, ?, ?)",
                (job_id, tag_id, now),
            )
        await db.commit()
    finally:
        await db.close()


async def batch_remove_tag(job_ids: list[str], tag_id: str) -> None:
    """Remove a tag from multiple notes."""
    if not job_ids:
        return
    db = await _get_db()
    try:
        placeholders = ",".join("?" for _ in job_ids)
        await db.execute(
            f"DELETE FROM note_tags WHERE tag_id = ? AND job_id IN ({placeholders})",
            [tag_id, *job_ids],
        )
        await db.commit()
    finally:
        await db.close()


async def batch_move_to_folder(job_ids: list[str], folder_id: str | None) -> None:
    """Move multiple notes to a folder (or uncategorized if folder_id is None)."""
    if not job_ids:
        return
    db = await _get_db()
    try:
        placeholders = ",".join("?" for _ in job_ids)
        await db.execute(
            f"UPDATE tasks SET folder_id = ? WHERE job_id IN ({placeholders})",
            [folder_id, *job_ids],
        )
        await db.commit()
    finally:
        await db.close()


async def batch_set_favorite(job_ids: list[str], is_favorite: bool) -> None:
    """Set favorite on multiple notes."""
    if not job_ids:
        return
    now = datetime.now(UTC).isoformat()
    favorited_at = now if is_favorite else None
    db = await _get_db()
    try:
        placeholders = ",".join("?" for _ in job_ids)
        await db.execute(
            f"UPDATE tasks SET is_favorite = ?, favorited_at = ?, updated_at = ? "
            f"WHERE job_id IN ({placeholders})",
            [1 if is_favorite else 0, favorited_at, now, *job_ids],
        )
        await db.commit()
    finally:
        await db.close()
