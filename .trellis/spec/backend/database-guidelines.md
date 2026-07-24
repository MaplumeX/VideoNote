# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

- **Database**: SQLite with WAL mode, accessed via `aiosqlite`
- **ORM**: None — raw SQL with parameterized queries
- **Migrations**: Manual `ALTER TABLE` in `init_db()`, no migration framework
- **Connection pattern**: Application-level singleton connection (managed by `init_db()` / `close_db()`)

---

## Query Patterns

### Singleton connection

All DB functions use a single shared `aiosqlite.Connection` managed by `init_db()` / `close_db()`. Functions call `_get_db()` to access the shared connection; they MUST NOT close it. aiosqlite serializes operations on a single connection internally, so this is thread-safe. WAL mode allows concurrent reads.

```python
# db.py
_db_conn: aiosqlite.Connection | None = None

async def _get_db() -> aiosqlite.Connection:
    global _db_conn
    if _db_conn is None:  # lazy init
        _db_conn = await aiosqlite.connect(str(DB_PATH))
        await _db_conn.execute("PRAGMA foreign_keys = ON")
        _db_conn.row_factory = aiosqlite.Row
    return _db_conn

async def init_db() -> None:
    global _db_conn
    _db_conn = await aiosqlite.connect(str(DB_PATH))
    await _db_conn.execute("PRAGMA journal_mode=WAL")
    await _db_conn.execute("PRAGMA foreign_keys = ON")
    _db_conn.row_factory = aiosqlite.Row
    # ... schema + migrations ...

async def close_db() -> None:
    global _db_conn
    if _db_conn is not None:
        await _db_conn.close()
        _db_conn = None

async def get_task(job_id: str) -> dict | None:
    db = await _get_db()  # shared connection — do NOT close
    cursor = await db.execute("SELECT * FROM tasks WHERE job_id = ?", (job_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)
```

`close_db()` is called in `main.py` lifespan `finally` block alongside `task_runner.shutdown()`. `init_db()` must run before any DB query.

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
    db = await _get_db()
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
    global _db_conn
    _db_conn = await aiosqlite.connect(str(DB_PATH))
    await _db_conn.execute("PRAGMA journal_mode=WAL")
    await _db_conn.execute("PRAGMA foreign_keys = ON")
    _db_conn.row_factory = aiosqlite.Row
    try:
        await _db_conn.executescript(_CREATE_TABLE_SQL)
        try:
            await _db_conn.execute("ALTER TABLE tasks ADD COLUMN user_id TEXT REFERENCES users(id)")
        except aiosqlite.OperationalError:
            pass  # Column already exists
        await _db_conn.commit()
    except Exception:
        await _db_conn.close()
        _db_conn = None
        raise
    await _cleanup_expired_tokens()
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

### Don't: Close the shared connection inside a DB function

The singleton connection is owned by `init_db()` / `close_db()`. Individual DB functions MUST NOT call `await db.close()` — it breaks all subsequent queries. For transactional functions using `BEGIN IMMEDIATE`, keep `await db.rollback()` on failure (rolls back the transaction without closing the connection).

### Don't: Use string formatting for queries

```python
# BAD — SQL injection
await db.execute(f"SELECT * FROM tasks WHERE job_id = '{job_id}'")

# GOOD — parameterized query
await db.execute("SELECT * FROM tasks WHERE job_id = ?", (job_id,))
```

### Don't: Store secrets in plaintext

API keys and cookies must be encrypted via `app/crypto.py` (Fernet) before storing in `user_providers.api_key_encrypted` or `user_cookies.cookie_encrypted`.

### Don't: Return encrypted secrets to the frontend

When querying tables with encrypted columns, **never include the encrypted column in SELECT** for API responses. Only return existence/metadata:

```python
# BAD — leaks encrypted content to frontend
cursor = await db.execute("SELECT * FROM user_cookies WHERE user_id = ?", (user_id,))

# GOOD — exclude encrypted column
cursor = await db.execute(
    "SELECT user_id, platform, updated_at FROM user_cookies WHERE user_id = ?",
    (user_id,),
)
```

For single-row lookups needed server-side (e.g., decrypting cookies for yt-dlp), use a dedicated internal function that returns the full row but is **never exposed via API**.

---

## Dynamic ORDER BY

When user input controls the sort column, use a **whitelist** — never interpolate directly:

```python
# BAD — SQL injection via sort_by
query = f"SELECT * FROM tasks ORDER BY {sort_by} {sort_order}"

# GOOD — whitelist validated column name
allowed_sort = {"created_at", "title", "stage"}
if sort_by in allowed_sort:
    sort_expr = f"t.{sort_by}"
else:
    sort_expr = "t.created_at"  # safe default
```

`sort_order` must also be validated: only `"ASC"` or `"DESC"`.

---

## Searching JSON Columns

`tasks.result_json` stores a JSON blob with fields like `title`. Since `title` isn't a real column, search it via `json_extract()`:

```python
# Search title inside result_json
conditions.append("json_extract(t.result_json, '$.title') LIKE ? ESCAPE '\\\\'")
params.append(_escape_like(search))
```

Similarly, sorting by a field that may live in JSON or a real column — use `COALESCE` to prefer the column:

```python
# title was extracted from result_json into a real column
sort_expr = "COALESCE(t.title, json_extract(t.result_json, '$.title'), '')"
```

> **Pattern**: When a JSON field is needed for sorting/filtering, extract it into a real column at insert time. Then use `COALESCE(column, json_extract(...))` during migration so both old rows (JSON-only) and new rows (column populated) work correctly.

### LIKE Wildcard Escaping

When building `LIKE` queries from user input (e.g. the `search` parameter), always escape `%` and `_` wildcards with the `_escape_like()` helper and add `ESCAPE '\\'` to the SQL clause. Otherwise, a user searching for `a_b` would match `axb`:

```python
# GOOD — escaped LIKE
def _escape_like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"

conditions.append("(t.message LIKE ? ESCAPE '\\' OR t.file_name LIKE ? ESCAPE '\\')")
params.extend([like, like])
```

### Explicit Transaction Locking

Functions that use explicit `BEGIN IMMEDIATE` transactions (`add_tags_to_note`, `batch_add_tag`) MUST be wrapped in `async with _tag_write_lock` (an `asyncio.Lock`). This prevents concurrency with auto-commit writes (e.g. `update_progress` from SSE) that share the singleton connection and would otherwise interleave as "cannot start a transaction within a transaction"

```python
_tag_write_lock = asyncio.Lock()

async def add_tags_to_note(job_id, user_id, tag_ids):
    async with _tag_write_lock:
        db = await _get_db()
        await db.execute("BEGIN IMMEDIATE")
        try:
            ...
            await db.commit()
        except Exception:
            await db.rollback()
            raise
```

### Terminal Task Cleanup

`cleanup_old_terminal_tasks(max_age_days=30)` deletes old terminal (complete/failed/cancelled) task rows at startup. Associated `note_tags` rows are removed via `ON DELETE CASCADE`. This complements `cleanup_failed_task_files` (which only nullifies `input_file_path` for 7-day-old failed tasks).

---

## Durable Single-Process Video Tasks

### 1. Scope / Trigger

Use this contract whenever a route creates, retries, cancels, deletes, recovers, or completes a long-running video task. It applies to the current single-process, single-image SQLite deployment; it is not a distributed leasing protocol.

### 2. Signatures

- Persist recovery input in `tasks.input_file_path`, cancellation intent in `tasks.cancel_requested`, and recovery count in `tasks.attempt_count`.
- Schedule work through the application `TaskRunner`; routes must not call bare `asyncio.create_task()` for video processing.
- Database helpers that mutate a task terminal/progress state must include the task id and enforce the cancellation/non-terminal predicate in the same SQL statement.
- Tag-association helpers must accept `user_id` and validate the note plus every tag inside one transaction.

### 3. Contracts

- A non-terminal task must either be scheduled after startup or be moved to an explicit recoverability failure.
- Upload source files remain on the persistent upload path until terminal completion, user cancellation, or terminal failure cleanup.
- User cancellation is durable before in-memory cancellation is requested.
- Progress and success writes are conditional on `cancel_requested = 0` and a non-terminal current stage.
- Shutdown cancellation preserves recoverable input and task state; user cancellation cleans input and keeps `cancelled`.
- Existing tag links are all-or-nothing and user-scoped. Cross-user historical links are removed by migration.

### 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Recoverable URL task | Schedule once and increment recovery attempt |
| Recoverable upload with valid persisted file | Schedule once using that file |
| Missing/invalid upload input | Fail with `TASK_RECOVERY_INPUT_INVALID` |
| Unsupported persisted URL/input | Fail with `TASK_RECOVERY_UNSUPPORTED_URL` |
| Cancellation races with progress/success | Conditional update affects zero rows; `cancelled` wins |
| Any requested tag is missing or belongs to another user | Roll back all links and return scoped 404 |

### 5. Good / Base / Bad

- Good: restart finds a valid pending upload and resumes it once.
- Base: a completed task is ignored by recovery and terminal writes remain idempotent.
- Bad: an invalid recovery input fails visibly instead of remaining indefinitely in `processing`.

### 6. Tests Required

- Migration compatibility for existing databases and cleanup of cross-user tag links.
- URL/upload recovery, invalid recovery input, scheduling deduplication, and shutdown semantics.
- Cancellation races against progress and result writes.
- Same-user tag association plus mixed valid/cross-user atomic rollback.
- External downloader, ASR, and LLM calls must be mocked.

### 7. Wrong vs Correct

```python
# WRONG — cancellation can commit between the SELECT and UPDATE.
task = await get_task(task_id)
if task["stage"] != "cancelled":
    await db.execute("UPDATE tasks SET stage = 'completed' WHERE id = ?", (task_id,))

# CORRECT — the state guard and write are one SQLite operation.
await db.execute(
    """
    UPDATE tasks
       SET stage = 'completed', result_json = ?
     WHERE id = ?
       AND cancel_requested = 0
       AND stage NOT IN ('completed', 'failed', 'cancelled')
    """,
    (result_json, task_id),
)
```
