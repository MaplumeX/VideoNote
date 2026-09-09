# Pipeline Contract (C1 Baseline)

> **Single source of truth** for the pipeline rewrite contract (subtasks C2–C5 and the
> frontend). Frozen at the G1 gate; any change to state/errors/progress semantics must go
> back to the parent task for review.
>
> Implementation: `backend/app/pipeline/` (state.py, errors.py, progress.py, stages/base.py).

## 1. Task Status & Pipeline Phase

The legacy single `TaskStage` enum is split into two dimensions:

```python
class TaskStatus(StrEnum):   # task lifecycle (persisted in tasks.status)
    pending    # created, not yet scheduled
    running    # executing; current phase is tasks.phase
    complete   # terminal
    failed     # terminal; reason in tasks.last_error_code
    cancelled  # terminal

class PipelinePhase(StrEnum):  # execution phase within a run (persisted in tasks.phase)
    fetching    # URL only: video metadata + thumbnail
    subtitle    # URL only: subtitle extraction (hit -> skip audio+transcribe)
    audio       # audio download / extraction
    transcribe  # ASR transcription
    notegen     # LLM note generation
```

`phase` is `NULL` when `status` is `pending` or terminal.

### 1.1 Paths

```
URL_PATH:  fetching → subtitle → audio → transcribe → notegen
FILE_PATH: audio → transcribe → notegen
```

### 1.2 Transition table (`ALLOWED_TRANSITIONS`)

| From | To |
|------|-----|
| *(start)* | `fetching`, `audio` |
| `fetching` | `subtitle` |
| `subtitle` | `audio` *(subtitle miss)*, `notegen` *(subtitle hit — skips audio+transcribe)* |
| `audio` | `transcribe` |
| `transcribe` | `notegen` |
| `notegen` | *(pipeline completes)* |

Rules:

- Phase transitions are phase-level only. Terminal statuses (`failed`/`cancelled`) are
  reachable from ANY phase and are validated at the `TaskStatus` level, not in the table.
- `validate_transition(src, dst)` raises `InvalidTransitionError` on illegal transitions.
- `validate_completion(phase)` — only `notegen` may complete the pipeline.
- `next_phases(path, current)` returns the legal successors within a path
  (`current=None` → valid starting phases).

ASCII diagram:

```
 (start) ──> fetching ──> subtitle ──miss──> audio ──> transcribe ──> notegen ──> (complete)
   │                        │                                ▲
   └──────────> audio ──────┴─────hit────────────────────────┘
```

### 1.3 Checkpoints

```python
@dataclass(frozen=True)
class Checkpoint:
    completed_phase: PipelinePhase   # last successfully finished phase
    artifacts: frozenset[ArtifactKind]
```

Resume rule — `resume_point(path, checkpoint) -> PipelinePhase`:

- No checkpoint → first phase of the path ("run from scratch"; this is also the semantics
  of legacy rows whose `checkpoint_phase` is NULL).
- Subtitle artifact present → resume at `notegen` (conditional skip).
- Otherwise → first allowed successor of `completed_phase` within the path. If the
  completed phase exhausted the path (`notegen`), re-run the final phase so the terminal
  write is idempotent.

## 2. Progress Model (SSE)

The global 0–1 percentage is **abolished**. Progress is two-level: `phase` + within-phase
fraction. A frontend wanting a total bar synthesizes it as
`(phase_index + phase_progress) / phase_count` per path.

### 2.1 `ProgressEvent` SSE payload schema

Emitted on the task progress stream (event: `progress`):

```json
{
  "status": "running",
  "phase": "transcribe",
  "phase_progress": 0.42,
  "message": "Transcribing chunk 2/4",
  "attempt": 1,
  "timestamp": "2025-01-01T12:00:00.123456+00:00"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `status` | enum string | `pending` \| `running` \| `complete` \| `failed` \| `cancelled` |
| `phase` | enum string \| null | `null` when `status` is `pending` or terminal |
| `phase_progress` | number ∈ [0,1] | within-phase fraction; **not** global |
| `message` | string | display text, or `SCREAMING_SNAKE_CASE` error code (optionally `"CODE: sanitized detail"`) |
| `attempt` | integer | execution attempt count (1-based first run) |
| `timestamp` | string | ISO 8601 UTC |

### 2.2 Monotonicity guard

`PhaseProgressTracker.update(phase, fraction)`:

- Clamps `fraction` to [0, 1].
- Within the same phase, fraction only ever moves **up**; a regression returns the
  running max and logs a warning.
- Switching phase resets the guard.

`ProgressPublisher` protocol (implemented by the orchestrator in C4):

```python
async def publish(self, phase: PipelinePhase, fraction: float, message: str) -> None: ...
```

### 2.3 REST changes (C4/C5 scope, noted here for planning)

- `POST /tasks/{id}/retry` — semantics enhanced: resumes from the persisted checkpoint.
- Other endpoint paths unchanged; response models switch to the new enums.
- **No compatibility layer** — frontend and backend switch together (D2).

### 2.4 REST response model changes (delivered in C4 — for C5)

All endpoint paths are unchanged; only payload models moved to the new contract.

| Endpoint | Model | Change |
|----------|-------|--------|
| `POST /api/tasks/{id}/retry` | `ProcessResponse` | `source_type` field added (`"url" | "upload"`); retry now resumes from `checkpoint_phase` (completed phases with durable artifacts are not re-executed; failed tasks retain their per-job WAV and upload input on disk to back this guarantee, removed only via task deletion or the 7-day delayed cleanup) |
| `GET /api/tasks/{id}/progress` (SSE) | `TaskProgress` (event: `progress`) | Replaced by the §2.1 `ProgressEvent` payload: `status` (new `TaskStatus`), `phase` (new `PipelinePhase`, nullable), `phase_progress` ∈ [0,1] within-phase (the global 0–1 `progress` value is abolished), `message`, `attempt`, `timestamp`. Terminal states additionally emit an `event: complete` with the raw `result_json` payload. Heartbeat: `event: ping` every 15 s; stream cap 30 min. |
| `GET /api/tasks` / `GET /api/tasks/{id}` | `TaskListItem` | `stage` field replaced by `status` (`TaskStatus`) + `phase` (`TaskPhase`\|null) + `phase_progress`; legacy rows are displayed via the backfilled `status` (`COALESCE`-style: old rows read the backfilled value, new rows the new columns) |
| `POST /api/process` | `ProcessResponse` | unchanged shape; `platform` validated before task creation |
| `POST /api/upload` | `UploadResponse` | unchanged |
| `GET /api/tasks/{id}/result` | `NoteResponse` | unchanged |
| `POST /api/tasks/{id}/cancel` | — | durable cancel intent write; converges to `status=cancelled`, `last_error_code=TASK_CANCELLED` within ≤ 3 s |

Migration note for the frontend (C5): the legacy `stage` enum
(`downloading`/`extracting_subtitles`/`transcribing`/`generating_notes`) no longer appears
in any API response; `phase` replaces it and is `null` unless `status=running`.

## 3. Intermediate Artifacts

Table `task_artifacts`:

```sql
CREATE TABLE IF NOT EXISTS task_artifacts (
    job_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (job_id, kind)
);
```

Kinds:

| Kind | Producer phase | Content |
|------|----------------|---------|
| `video_meta` | `fetching` | JSON object (title, duration, thumbnail ref, …) |
| `subtitle` | `subtitle` | Subtitle text (plain string) |
| `transcript` | `transcribe` | Transcript text (plain string) |
| `notes_draft` | `notegen` | *Reserved* for C3 multi-chunk intermediate state; no writer in C1 |

DB API: `save_artifact(job_id, kind, content)` (UPSERT), `get_artifact(job_id, kind)`.
Plain strings are stored as `{"text": "..."}`; the reader unwraps single-`text` objects
transparently.

## 4. Error Codes

All pipeline failures carry a stable code from `app.pipeline.errors.ErrorCode`. Raw
exception text stays in server logs only.

| Code | When |
|------|------|
| `VIDEO_PRIVATE` | yt-dlp: private video |
| `VIDEO_GEO_RESTRICTED` | yt-dlp: geo/region restriction |
| `VIDEO_NOT_FOUND` | yt-dlp: 404 / deleted / unavailable |
| `VIDEO_COOKIE_INVALID` | yt-dlp: cookie/login required |
| `VIDEO_FETCH_FAILED` | video fetch catch-all |
| `SUBTITLE_EXTRACTION_FAILED` | subtitle stage failed |
| `AUDIO_EXTRACTION_FAILED` | audio download/extraction failed (also for uploads; never reuse `VIDEO_FETCH_FAILED` for upload-source tasks) |
| `TRANSCRIPTION_FAILED` | ASR stage failed |
| `NOTE_GENERATION_FAILED` | LLM note generation failed |
| `PROCESSING_FAILED` | catch-all unexpected failure |
| `PROVIDER_NOT_CONFIGURED` | ASR or LLM provider incomplete (key/base/model) |
| `TASK_RECOVERY_MAX_ATTEMPTS` | recovery skipped: attempt count exhausted (max 5) |
| `TASK_RECOVERY_INPUT_INVALID` | recovery input missing/invalid |
| `TASK_RECOVERY_UNSUPPORTED_URL` | persisted URL not YouTube/Bilibili |
| `TASK_CANCELLED` | task was cancelled |

Non-pipeline codes (e.g. `MODELS_FETCH_FAILED`) stay in `app/errors.py` — not migrated.

### 4.1 `PipelineError` & sanitization

```python
class PipelineError(Exception):
    code: ErrorCode
    detail: str  # sanitized at construction, ≤ 200 chars
```

- `detail` is sanitized **at construction** (`sk-*` API keys, `Bearer` tokens, and
  `Cookie:`/`Set-Cookie:` headers redacted to `[REDACTED]`; stripped and truncated to
  200 chars). Reading `error.detail` is therefore always safe — forgetting to sanitize is
  structurally impossible.
- `sanitize_detail(text)` is the single centralized implementation.

## 5. Stage Interface (C2/C3 implementation contract)

```python
@dataclass
class StageContext:
    job_id: str
    language: str
    provider: ProviderConfig            # asr/llm ProviderEndpoint: api_key/api_base/model/provider
    artifacts: ArtifactStore            # get(kind) / put(kind, content), DB-backed
    progress: ProgressPublisher
    register_cancel: CancelHandleRegistrar  # register/unregister a kill/cancel handle
    extra: dict[str, object]            # task-level inputs: "url", "input_path", "cookiefile"

@dataclass
class StageResult:
    outputs: dict[ArtifactKind, object] # persisted by the orchestrator
    extra: dict[str, object]            # non-artifact values (see below)

class Stage(Protocol):
    phase: ClassVar[PipelinePhase]
    async def run(self, ctx: StageContext, *, resume: bool) -> StageResult: ...
```

- `resume=True` tells the stage a checkpoint exists; it may skip work whose outputs are
  already in the artifact store.
- `StageContext.extra` carries task-level inputs that are not artifacts: the source
  `url` (fetch/subtitle/audio for URL tasks), the uploaded `input_path` (audio for
  file tasks), and the per-user `cookiefile` temp path (URL tasks whose user has a
  per-platform cookie; passed to every yt-dlp call of the run — fetch/subtitle/audio;
  the orchestrator materializes and cleans up the file), injected by the orchestrator
  from the task row.
- `StageResult.extra` carries values that are not artifacts: C2's `audio_path` (path to
  the extracted audio for the next stage) and C3's `notes` (the final note text — the
  orchestrator writes it to `tasks.result_json`, matching the legacy chain; `notes` is
  deliberately NOT an `ArtifactKind`).
- The cancel handle terminates in-flight work (subprocess kill or asyncio cancel); the
  orchestrator (C4) invokes it. Registering `None` unregisters.

### 5.1 Transcription-side stage semantics (C2)

- `fetching`: yt-dlp CLI `--dump-json --no-download` for title/thumbnail; stderr text is
  classified by the legacy keyword table into the `VIDEO_*` codes. Thumbnail download
  (httpx async, Bilibili Referer) is non-fatal. Output: `video_meta` artifact
  (`{title, thumbnail}`; thumbnail is a local filename under `UPLOAD_DIR/thumbnails`).
- `subtitle`: yt-dlp CLI `--write-subs --write-auto-subs --convert-subs srt
  --skip-download`; language priority follows the note language (`zh*` →
  `zh-Hans,zh,en,ja`, else `en,zh-Hans,zh,ja`). Hit → `subtitle` artifact; miss →
  **empty outputs** (the orchestrator follows the transition table to `audio`); yt-dlp
  failure → `SUBTITLE_EXTRACTION_FAILED`.
- `audio`: URL tasks run yt-dlp `-f bestaudio/best` then ffmpeg WAV conversion
  (pcm_s16le/16 kHz/mono); file (upload) tasks run ffmpeg only and failures are
  `AUDIO_EXTRACTION_FAILED` (never `VIDEO_FETCH_FAILED`). The WAV path is passed via
  `StageResult.extra["audio_path"]`; the orchestrator owns its cleanup after the run.
  Cleanup is terminal-state dependent: `complete`/`cancelled` delete the per-job WAV
  and the upload input immediately; `failed` **keeps both** on disk so a retry can
  resume from the checkpoint (see §7); deleting the task removes them, and the
  delayed housekeeping (`cleanup_failed_task_files`, 7 days) is the safety net.
  When a retry resumes past `audio` but the WAV is gone, only the `audio` phase
  re-runs — the checkpoint's artifacts stay, so fetch/subtitle remain skipped.
- `transcribe`: Async [OI] ASR. Provider incomplete → `PROVIDER_NOT_CONFIGURED`.
  File ≤ 25 MB ([OI]-compatible) / 50 MB (SiliconFlow) → single call; over the limit →
  ffprobe duration probe + ffmpeg chunk split + per-chunk timestamp offsetting. Chunk
  progress publishes `start/total`. ASR failures wrap into `TRANSCRIPTION_FAILED`.
- Subprocess management (`app/pipeline/subprocess_util.py`): all yt-dlp/ffmpeg/ffprobe
  calls go through `run_managed_process` (exec list args, cancel handle → SIGTERM →
  SIGKILL after 5 s, timeout- and cancellation-safe, no process leaks). Shared yt-dlp
  argv building (`build_ytdlp_args`) preserves proxy/cookie/browser-cookie semantics;
  `classify_ytdlp_error(text) -> ErrorCode` migrates the legacy keyword table.

### 5.2 notegen stage semantics (C3)

- Input: the `transcript` artifact (guaranteed by the transition table; missing →
  defensive `PROCESSING_FAILED`). `PROVIDER_NOT_CONFIGURED` is raised inside the stage
  when the LLM endpoint is incomplete.
- Transcript > 60000 chars is split at line boundaries (oversize single lines kept as-is);
  per-chunk sub-notes are generated and merged with a final LLM call.
- Within-phase progress: single chunk → `0.0` ("Generating notes...") → `1.0` ("Notes
  generated"). Multi-chunk → chunk *i* publishes `(i+1)/n * 0.9` ("Generating notes
  i/n"), merge → `0.9` ("Merging notes..."), done → `1.0` ("Notes generated"). All
  within-phase fractions are monotonic via `PhaseProgressTracker`.
- Cancellation: every chunk/merge call is a separate `await` on the async LLM client;
  `asyncio.Task.cancel()` aborts the in-flight request and no further calls start.
- `resume=True` re-runs the whole phase (sub-notes are not persisted); LLM calls are
  side-effect free, so this is idempotent.

## 6. DB Schema Additions (backward compatible)

New columns on `tasks` (legacy `stage`/`progress` columns stay untouched until C4):

| Column | Type | Notes |
|--------|------|-------|
| `status` | TEXT | new `TaskStatus` value; NULL on rows created by the new chain before first write |
| `phase` | TEXT | current `PipelinePhase`; NULL when not running |
| `phase_progress` | REAL | within-phase fraction |
| `checkpoint_phase` | TEXT | last completed phase; NULL = run from scratch |
| `last_error_code` | TEXT | error code for `failed` tasks |

One-time backfill (idempotent via `WHERE status IS NULL`): legacy `stage` →
`pending`→`pending`; `downloading`/`extracting_subtitles`/`transcribing`/`generating_notes`→`running`;
`complete`/`failed`/`cancelled`→same name. `checkpoint_phase` stays NULL for legacy rows.

Conditional writes (`save_checkpoint`) follow the Durable Single-Process Video Tasks
contract: the state guard and the write are one SQLite operation guarded by
`cancel_requested = 0` AND non-terminal `status`/`stage` — cancellation and terminal
states always win races against progress/checkpoint writes.
