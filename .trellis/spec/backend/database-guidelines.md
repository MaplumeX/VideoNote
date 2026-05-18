# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

- **Database**: SQLite with WAL mode, accessed via `aiosqlite`
- **ORM**: None — raw SQL with parameterized queries
- **Migrations**: Manual `ALTER TABLE` in `init_db()`, no migration framework
- **Connection pattern**: Open/close per operation (`aiosqlite.connect` as context manager)

---

## Query Patterns

### One-off queries

Each DB function opens its own connection. No connection pooling (aiosqlite handles this internally with WAL).

```python
# db.py
async def get_task(job_id: str) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks WHERE job_id = ?", (job_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
```

### Row factory

Always set `db.row_factory = aiosqlite.Row` when you need dict-like access to results.

### UPSERT pattern

Use `ON CONFLICT ... DO UPDATE` for upserts:

```python
# db.py — save_provider_config
INSERT INTO user_providers (...) VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(user_id, category) DO UPDATE SET ...
```

### Batch reads

Fetch multiple rows with `fetchall()`, convert with list comprehension:

```python
async def get_user_tasks(user_id: str) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT ... FROM tasks WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
```

---

## Migrations

Migrations are ad-hoc `ALTER TABLE` statements inside `init_db()`, wrapped in try/except to handle already-applied changes:

```python
async def init_db() -> None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN user_id TEXT REFERENCES users(id)")
        except aiosqlite.OperationalError:
            pass  # Column already exists
        await db.executescript(_CREATE_TABLE_SQL)
        await db.commit()
```

- `CREATE TABLE IF NOT EXISTS` for initial schema
- `ALTER TABLE` with `try/except OperationalError` for new columns
- No version tracking — if the schema gets complex, add a `schema_version` table

---

## Naming Conventions

- **Table names**: `snake_case`, plural (`tasks`, `users`, `refresh_tokens`, `user_providers`)
- **Column names**: `snake_case` (`job_id`, `password_hash`, `created_at`, `api_key_encrypted`)
- **Primary keys**: `id` or `job_id` (domain-specific)
- **Foreign keys**: `<referenced_table_singular>_id` (`user_id` references `users.id`)
- **Timestamps**: `created_at`, `updated_at`, `expires_at`, `revoked_at` (stored as ISO 8601 text)
- **Indexes**: `idx_<table>_<column>` (`idx_refresh_tokens_user_id`, `idx_refresh_tokens_token_hash`)

---

## Common Mistakes

### Don't: Forget `await db.commit()` after writes

aiosqlite does not auto-commit. Without `commit()`, changes are lost.

### Don't: Use string formatting for queries

```python
# BAD — SQL injection
await db.execute(f"SELECT * FROM tasks WHERE job_id = '{job_id}'")

# GOOD — parameterized query
await db.execute("SELECT * FROM tasks WHERE job_id = ?", (job_id,))
```

### Don't: Store secrets in plaintext

API keys must be encrypted via `app/crypto.py` (Fernet) before storing in `user_providers.api_key_encrypted`.
