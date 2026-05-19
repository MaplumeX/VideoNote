# Research: Tags + Folders Schema Design for VideoNote

- **Query**: Best data model and API design for implementing tags + folders organization for notes in a SQLite-backed app (FastAPI + aiosqlite)
- **Scope**: mixed (internal codebase analysis + external pattern research)
- **Date**: 2026-05-19

## Findings

### Current Schema State

| File Path | Description |
|---|---|
| `backend/app/db.py` | Database layer: all table DDL, CRUD functions, migration logic |
| `backend/app/schemas.py` | Pydantic models: TaskListItem, TaskListResponse, NoteResponse, etc. |
| `backend/app/api/routes.py` | FastAPI routes: /process, /upload, /tasks, /settings |
| `backend/app/api/auth_routes.py` | Auth routes: /auth/register, /login, /refresh, /logout, /me |
| `backend/app/main.py` | App setup: CORS, router mounting, lifespan with init_db() |
| `.trellis/spec/backend/database-guidelines.md` | Project DB conventions: raw SQL, aiosqlite, manual migrations, naming |

#### Current `tasks` table columns

```
job_id TEXT PRIMARY KEY,
user_id TEXT,
stage TEXT NOT NULL DEFAULT 'pending',
progress REAL NOT NULL DEFAULT 0.0,
message TEXT NOT NULL DEFAULT '',
result_json TEXT,            -- stores JSON {"markdown": "...", "title": "..."}
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
video_url TEXT,              -- added via ALTER TABLE migration
file_name TEXT,              -- added via ALTER TABLE migration
platform TEXT,               -- added via ALTER TABLE migration
language TEXT,               -- added via ALTER TABLE migration
source_type TEXT,            -- added via ALTER TABLE migration
```

#### Current migration pattern (db.py:62-85)

Migrations are ad-hoc `ALTER TABLE ADD COLUMN` inside `init_db()`, wrapped in `try/except aiosqlite.OperationalError` for idempotency. No version tracking. No migration framework.

#### Key observation: `PRAGMA foreign_keys = ON` is NOT set

Current `init_db()` sets `PRAGMA journal_mode=WAL` but does **not** enable `PRAGMA foreign_keys = ON`. Without this, all `ON DELETE CASCADE` / `ON DELETE SET NULL` clauses in FK definitions are silently ignored by SQLite. This must be added per-connection (cannot be set inside a transaction).

---

### Schema Design Options

#### 1. Tags: Junction Table vs JSON Column

| Aspect | Junction Table | JSON Column |
|---|---|---|
| **Tables needed** | `tags` + `note_tags` | None (add `tags TEXT` to `tasks`) |
| **Referential integrity** | Yes (FK constraints) | No |
| **Tag rename** | Single row update in `tags` | Update JSON in every affected `tasks` row |
| **Tag delete** | CASCADE removes associations | Must update JSON in every affected row |
| **Filter by tag** | JOIN with index, O(log N) | `json_each()` scan, O(N), no index |
| **Tag metadata** | Easy (add columns to `tags`) | Not possible |
| **Deduplication** | Enforced by UNIQUE on tag name | Must enforce in app logic |
| **Complexity** | More tables, more joins | Simpler, fewer tables |
| **SQLite suitability** | Standard relational pattern | Works but limited for filtering |

**Pattern used by SQLite-backed note apps**: Joplin and Standard Notes both use junction tables for tags.

**For this project**: Junction table is the better choice because:
- Tag rename/delete is a core user operation (needs to be efficient)
- Tag metadata (color, usage count) is a natural extension
- The project already uses relational patterns (FK on `user_id`, `refresh_tokens`)
- Dataset size is small enough that join performance is not a concern

#### 2. Folders: Tree Structure Patterns

| Pattern | Read Subtree | Move Node | Insert | Complexity | SQLite Support |
|---|---|---|---|---|---|
| **Adjacency List** (parent_id) | WITH RECURSIVE CTE | O(1) update parent_id | O(1) insert | Low | CTE since 3.8.3 |
| **Materialized Path** (/1/4/7/) | LIKE '/1/4/%' | Rewrite all paths in subtree | O(1) insert | Medium | Good |
| **Nested Sets** (lft/rgt) | WHERE lft BETWEEN | Rewrite half the tree | Rewrite half the tree | High | Good but fragile |
| **Flat** (folder_id on tasks only) | N/A (no nesting) | O(1) update folder_id | O(1) | Lowest | Trivial |

**Pattern used by note apps**:
- **Joplin**: Adjacency list (parent_id on folders table). A note belongs to exactly one folder.
- **Obsidian**: Real filesystem directories (effectively adjacency list).
- **Apple Notes**: Flat folders (no nesting, or 1-level only).
- **Notion**: Page tree = adjacency list, unlimited depth.

**For this project**: Adjacency list is the standard choice:
- Intuitive model (folder has parent folder)
- Easy to move nodes (just change parent_id)
- SQLite CTE handles subtree queries well
- Matches user mental model from file systems
- Depth can be soft-limited in UI (2-3 levels typical for personal notes)

#### 3. Favorites: Boolean Column vs Separate Table

| Aspect | Boolean Column | Separate Table |
|---|---|---|
| **Storage** | `is_favorite INTEGER DEFAULT 0` on `tasks` | `favorites(job_id, user_id)` |
| **Query** | WHERE is_favorite = 1 | JOIN favorites |
| **Simplicity** | Very simple | Unnecessary for 1:1 relationship |
| **Extensibility** | N/A (favorite is boolean) | Could store favorited_at, etc. |

**For this project**: Boolean column on `tasks` is sufficient. Favorites is a simple toggle, not a many-to-many relationship. Adding `favorited_at TEXT` alongside `is_favorite INTEGER` would preserve ordering info if needed.

---

### Proposed Schema (DDL)

```sql
-- Tags table (user-scoped, unique name per user)
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

-- Folders table (adjacency list, user-scoped)
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

-- Note-Tags junction table (many-to-many)
CREATE TABLE IF NOT EXISTS note_tags (
    job_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, tag_id),
    FOREIGN KEY (job_id) REFERENCES tasks(job_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id);

-- New columns on tasks table (via ALTER TABLE in init_db)
-- ALTER TABLE tasks ADD COLUMN folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL;
-- ALTER TABLE tasks ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0;
-- ALTER TABLE tasks ADD COLUMN favorited_at TEXT;

CREATE INDEX IF NOT EXISTS idx_tasks_folder_id ON tasks(folder_id);
CREATE INDEX IF NOT EXISTS idx_tasks_is_favorite ON tasks(is_favorite);
```

#### Key design decisions in proposed schema:

1. **Tags are user-scoped** (`user_id` on `tags`) -- prevents cross-user tag visibility
2. **Tag names are unique per user** (`UNIQUE(user_id, name)`) -- avoids duplicate "ai" tags
3. **Folder parent_id is nullable** -- NULL = root-level folder
4. **Folder ON DELETE CASCADE on parent_id** -- deleting a folder cascades to subfolders; notes in those folders get `folder_id SET NULL` (become uncategorized)
5. **note_tags ON DELETE CASCADE** -- deleting a tag or task auto-removes junction rows
6. **folder_id ON DELETE SET NULL on tasks** -- deleting a folder does NOT delete notes; notes become uncategorized
7. **is_favorite as INTEGER** -- SQLite has no boolean type; 0/1 convention

#### Cycle prevention in adjacency list:

SQLite cannot enforce "no cycles" via CHECK constraints (cannot reference other rows). Must validate in application code before updating `parent_id`:

```python
async def _would_create_cycle(db, folder_id: str, new_parent_id: str) -> bool:
    """Walk up from new_parent_id; if we reach folder_id, it's a cycle."""
    current = new_parent_id
    while current:
        if current == folder_id:
            return True
        cursor = await db.execute("SELECT parent_id FROM folders WHERE id = ?", (current,))
        row = await cursor.fetchone()
        current = row["parent_id"] if row else None
    return False
```

---

### API Design

#### Folders CRUD

| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| GET | `/api/folders` | List all folders for user (flat list) | - |
| GET | `/api/folders/tree` | Folder tree with nesting + note counts | - |
| POST | `/api/folders` | Create folder | `{name, parent_id?}` |
| GET | `/api/folders/{folder_id}` | Get folder details | - |
| PUT | `/api/folders/{folder_id}` | Update folder (rename, move) | `{name?, parent_id?}` |
| DELETE | `/api/folders/{folder_id}` | Delete folder (subfolders cascade, notes uncategorized) | - |
| GET | `/api/folders/{folder_id}/notes` | List notes in folder (paginated) | `?page=1&limit=20` |

#### Tags CRUD

| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| GET | `/api/tags` | List all tags for user (with note counts) | - |
| POST | `/api/tags` | Create tag | `{name, color?}` |
| PUT | `/api/tags/{tag_id}` | Rename tag / update color | `{name?, color?}` |
| DELETE | `/api/tags/{tag_id}` | Delete tag (removes all associations) | - |
| GET | `/api/tags/{tag_id}/notes` | List notes with this tag (paginated) | `?page=1&limit=20` |

#### Note-Tag Association

| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| POST | `/api/tasks/{job_id}/tags` | Add tag(s) to note | `{tag_ids: [str]}` or `{tag_names: [str]}` |
| DELETE | `/api/tasks/{job_id}/tags/{tag_id}` | Remove tag from note | - |

Design note on `POST /tasks/{job_id}/tags`: Two approaches:
- **By tag_id**: Client must create tag first, then associate. More rigid.
- **By tag_name**: Auto-create tag if not exists (like Notion/Obsidian). More user-friendly.
- **Hybrid**: Accept `tag_ids` for existing tags, `tag_names` for auto-creation. Most flexible.

#### Note-Folder Association

| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| PUT | `/api/tasks/{job_id}/folder` | Move note to folder | `{folder_id: str \| null}` |
| DELETE | `/api/tasks/{job_id}/folder` | Remove note from folder (set null) | - |

Note: `PUT` with `{folder_id: null}` is equivalent to `DELETE`, making `DELETE` endpoint optional.

#### Favorites

| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| PUT | `/api/tasks/{job_id}/favorite` | Set/unset favorite | `{is_favorite: bool}` |

#### Enhanced Task Listing (filter params on existing endpoint)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/tasks?folder={id}` | Filter by folder |
| GET | `/api/tasks?tag={id}` | Filter by tag |
| GET | `/api/tasks?is_favorite=true` | Filter by favorite |
| GET | `/api/tasks?folder={id}&tag={id}` | Combine filters |

The existing `GET /api/tasks` endpoint (routes.py:395-414) already supports `page` and `limit`. Add optional `folder`, `tag`, `is_favorite` query parameters.

SQL for filtered task listing with tags:
```sql
-- Filter by tag (join through note_tags)
SELECT DISTINCT t.job_id, t.stage, t.progress, t.message, t.created_at, ...
FROM tasks t
JOIN note_tags nt ON t.job_id = nt.job_id
WHERE t.user_id = ? AND nt.tag_id = ?
ORDER BY t.created_at DESC
LIMIT ? OFFSET ?;

-- Filter by folder
SELECT t.job_id, ... FROM tasks t
WHERE t.user_id = ? AND t.folder_id = ?
ORDER BY t.created_at DESC
LIMIT ? OFFSET ?;

-- Filter by favorite
SELECT t.job_id, ... FROM tasks t
WHERE t.user_id = ? AND t.is_favorite = 1
ORDER BY t.created_at DESC
LIMIT ? OFFSET ?;
```

#### Batch Operations

| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| POST | `/api/tasks/batch/tag` | Add tag to multiple notes | `{job_ids: [str], tag_id: str}` |
| POST | `/api/tasks/batch/move` | Move notes to folder | `{job_ids: [str], folder_id: str}` |
| POST | `/api/tasks/batch/favorite` | Set favorite on multiple notes | `{job_ids: [str], is_favorite: bool}` |
| DELETE | `/api/tasks/batch/tag` | Remove tag from multiple notes | `{job_ids: [str], tag_id: str}` |

#### Folder Tree Endpoint Response Format

```json
GET /api/folders/tree
{
  "folders": [
    {
      "id": "uuid-1",
      "name": "Project Alpha",
      "parent_id": null,
      "note_count": 5,
      "children": [
        {
          "id": "uuid-2",
          "name": "Research",
          "parent_id": "uuid-1",
          "note_count": 3,
          "children": []
        }
      ]
    }
  ]
}
```

Tree can be built in application code from a flat list (single query), then nested in Python:

```python
async def get_folder_tree(user_id: str) -> list[dict]:
    # 1. Fetch all folders for user
    # 2. Fetch note counts per folder
    # 3. Build tree in Python from flat list
    # 4. Return nested structure
```

---

### How Popular Note Apps Model This

| App | Tags | Folders | Storage | Notes in Folder | Tags per Note |
|---|---|---|---|---|---|
| **Joplin** | Junction table (note_tags) | Adjacency list (parent_id) | SQLite | Exactly 1 | Many |
| **Standard Notes** | Junction table (taggings) | Folders = tags with `is_tag=false` | SQLite | 1 (via "tag") | Many |
| **Obsidian** | Inline `#tag` in markdown | Filesystem directories | File system | Exactly 1 | Many |
| **Apple Notes** | Inline `#hashtag` | Flat folders (1 level) | Core Data | Exactly 1 | Many |
| **Notion** | Multi-select property | Page tree (adjacency list) | PostgreSQL + JSONB | 1 parent | Many (as property) |

**Common pattern across all apps**:
- A note belongs to **exactly one folder** (or none / uncategorized)
- A note can have **many tags**
- Tags and folders are **orthogonal dimensions** (can use both simultaneously)
- Folder = location, Tag = attribute

---

### Migration Strategy

All changes are **additive** -- no existing columns or data are modified.

#### Migration steps (applied in `init_db()`):

```python
# 1. Enable foreign keys per-connection (CRITICAL)
# Must be done in every async with aiosqlite.connect() block
await db.execute("PRAGMA foreign_keys = ON")

# 2. Create new tables (idempotent via IF NOT EXISTS)
await db.executescript("""
    CREATE TABLE IF NOT EXISTS tags (...);
    CREATE TABLE IF NOT EXISTS folders (...);
    CREATE TABLE IF NOT EXISTS note_tags (...);
    -- indexes
""")

# 3. Add new columns to tasks (idempotent via try/except)
for col_def in [
    "ALTER TABLE tasks ADD COLUMN folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL",
    "ALTER TABLE tasks ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tasks ADD COLUMN favorited_at TEXT",
]:
    try:
        await db.execute(col_def)
    except aiosqlite.OperationalError:
        pass  # Column already exists

# 4. Create indexes (idempotent via IF NOT EXISTS)
await db.executescript("""
    CREATE INDEX IF NOT EXISTS idx_tags_user_id ON tags(user_id);
    CREATE INDEX IF NOT EXISTS idx_folders_user_id ON folders(user_id);
    CREATE INDEX IF NOT EXISTS idx_folders_parent_id ON folders(parent_id);
    CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_folder_id ON tasks(folder_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_is_favorite ON tasks(is_favorite);
""")
```

#### Foreign key pragma placement:

The `PRAGMA foreign_keys = ON` must be set on **every connection**, not just at init time. Two options:

1. **In `init_db()` only**: Only FKs created during init are enforced. Other operations miss it. NOT sufficient.
2. **In a shared connection helper**: Create a utility that opens a connection and always sets the pragma:

```python
async def _get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    await db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = aiosqlite.Row
    return db
```

Then refactor all existing `async with aiosqlite.connect(str(DB_PATH)) as db:` to use this helper. This is the correct approach but requires touching all existing DB functions.

**Alternative (minimal change)**: Add pragma to `init_db()` for schema creation, and add it to the 3-4 functions that will write to the new tables (folder/tag CRUD). Existing functions that only read don't strictly need it. But for correctness, all connections should enable it.

#### No data migration needed

Existing `tasks` rows will have:
- `folder_id = NULL` (uncategorized -- the default, correct)
- `is_favorite = 0` (not favorited -- the default, correct)
- No `note_tags` rows (no tags -- correct, tags are added by user action)

No data backfill or transformation is required.

#### Schema version tracking

The current project has no version tracking. The spec (database-guidelines.md:83) says: "if the schema gets complex, add a `schema_version` table". With 3 new tables + 3 new columns, this is a good time to add it:

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

### Caveats / Not Found

1. **PRAGMA foreign_keys = ON is missing** from current codebase. All FK constraints in existing tables (`refresh_tokens.user_id`, `user_providers.user_id`) are currently NOT enforced. This is a pre-existing issue that the new schema depends on being fixed.

2. **Folder deletion with subfolders**: The proposed `ON DELETE CASCADE` on `folders.parent_id` means deleting a folder recursively deletes all subfolders. Notes in those folders get `folder_id SET NULL`. This is the Joplin pattern. An alternative (move subfolders to parent) requires application-level logic.

3. **Cycle prevention**: No SQL-level enforcement for adjacency list cycles. Must validate in Python before `parent_id` updates.

4. **Count queries for folder tree**: Getting `note_count` per folder requires either a separate query or a subquery. For a small number of folders (<100), this is fine.

5. **Batch operations**: The batch endpoints use `/api/tasks/batch/*` path, which could conflict with `/api/tasks/{job_id}` if FastAPI route ordering is not careful. Ensure `batch` is not a valid UUID or define the batch routes before the parameterized routes.

6. **Tag auto-creation**: When adding tags to notes by name, the "create if not exists" pattern needs careful concurrency handling (two requests creating the same tag name). The `UNIQUE(user_id, name)` constraint plus `INSERT ... ON CONFLICT DO NOTHING RETURNING id` handles this in SQLite.
