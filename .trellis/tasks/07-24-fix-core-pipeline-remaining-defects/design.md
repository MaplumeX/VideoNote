# 技术设计：修复核心链路剩余逻辑缺陷与体验问题

## 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/services/transcribe.py` | R4 切分健壮化、R5 进度回调 |
| `backend/app/services/note_gen.py` | R8 LLM 重试、R9 分块生成 |
| `backend/app/services/subtitle.py` | R7 `classify_ytdlp_error` helper |
| `backend/app/api/routes.py` | R1 字幕语言、R2 缩略图隔离、R5 进度回调胶水、R6 SSE 超时心跳、R7 错误码消费、R11 进度统一 |
| `backend/app/db.py` | R3 失败文件清理、R10 单例连接 |
| `backend/app/main.py` | R3 lifespan 调用清理、R10 lifespan 关闭连接 |
| `frontend/src/api/client.ts` | R7 新增错误码加入 `TASK_MESSAGE_ERROR_CODES` |
| `frontend/src/i18n/locales/en.json` | R7 新增错误码 i18n key |
| `frontend/src/i18n/locales/zh-CN.json` | R7 新增错误码 i18n key |

## 设计决策

### D1: 字幕语言重排（R1）

在 `routes.py` 增加模块级 helper：

```python
def _subtitle_languages(note_lang: str) -> list[str]:
    if note_lang.startswith("zh"):
        return ["zh-Hans", "zh", "en", "ja"]
    return ["en", "zh-Hans", "zh", "ja"]
```

调用处：`extract_subtitles(url, languages=_subtitle_languages(language), cookiefile_path=cookiefile_path)`。

### D2: 缩略图隔离（R2）

`_process_video_url` 的 video info try 块拆分：

```python
# 1. video info（致命）
try:
    video_info = await asyncio.to_thread(get_video_info, url, cookiefile_path=...)
    video_title = video_info["title"]
    ext_thumb = video_info.get("thumbnail_url") or ""
except asyncio.CancelledError:
    raise
except Exception as e:
    logger.exception(...)
    code = getattr(e, "code", None) or classify_ytdlp_error(e)  # R7
    await update_progress(job_id, TaskStage.failed, 0.0, code)
    return

# 2. 缩略图（非致命）
thumbnail_filename = None
if ext_thumb:
    try:
        thumbnail_filename = await asyncio.to_thread(download_thumbnail, ext_thumb)
    except Exception:
        logger.warning(f"Thumbnail download failed for {job_id}", exc_info=True)
await update_task_meta(job_id, video_title, thumbnail_filename)
```

### D3: 失败文件清理（R3）

`db.py` 新增：

```python
async def cleanup_failed_task_files(max_age_days: int = 7) -> int:
    """Delete input files for failed tasks older than max_age_days. Returns count."""
    cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT job_id, input_file_path FROM tasks "
            "WHERE stage = ? AND created_at < ? AND input_file_path IS NOT NULL",
            (TaskStage.failed.value, cutoff),
        )
        rows = await cursor.fetchall()
        count = 0
        for row in rows:
            path = Path(row["input_file_path"])
            # 路径安全：必须在 UPLOAD_DIR 下
            upload_root = UPLOAD_DIR.resolve()
            resolved = path.resolve()
            if resolved != upload_root and upload_root in resolved.parents:
                resolved.unlink(missing_ok=True)
                await db.execute(
                    "UPDATE tasks SET input_file_path = NULL WHERE job_id = ?",
                    (row["job_id"],),
                )
                count += 1
        await db.commit()
        return count
    finally:
        await db.close()
```

`main.py` lifespan 中调用，在 `recover_incomplete_tasks` 之后：

```python
async def lifespan(app):
    await init_db()
    await recover_incomplete_tasks()
    cleaned = await cleanup_failed_task_files()
    if cleaned:
        logger.info(f"Cleaned up {cleaned} failed task files")
    ...
```

### D4: 大文件 ASR 切分健壮化（R4）

`_transcribe_large_file` 修改：

```python
def _transcribe_large_file(client, audio_path, language, model, provider, progress_cb=None):
    probe_cmd = [...]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")
    try:
        total_seconds = float(result.stdout.strip())
    except ValueError as e:
        raise RuntimeError(f"ffprobe returned invalid duration: {result.stdout!r}") from e
    if total_seconds <= 0:
        raise RuntimeError(f"Invalid audio duration: {total_seconds}")

    max_size = ...
    ratio = max_size / os.path.getsize(audio_path) * 0.9
    # 最小 30 秒，最大 600 秒
    chunk_duration = max(min(total_seconds * ratio, 600), 30.0)

    full_transcript_parts = []
    with tempfile.TemporaryDirectory() as tmpdir:
        start = 0.0
        chunk_idx = 0
        while start < total_seconds:
            # ... split + transcribe ...
            if progress_cb:
                progress_cb(start / total_seconds, f"Transcribing chunk {chunk_idx + 1}...")
            start += chunk_duration
            chunk_idx += 1
    return "\n".join(full_transcript_parts)
```

### D5: 进度回调胶水（R5）

`transcribe_audio` 签名增加 `progress_cb`，透传给 `_transcribe_large_file`。

`routes.py` 中构造回调：

```python
loop = asyncio.get_running_loop()

def _asr_progress_cb(fraction: float, msg: str) -> None:
    # 映射到 0.4–0.6 区间
    progress = 0.4 + fraction * 0.2
    asyncio.run_coroutine_threadsafe(
        update_progress(job_id, TaskStage.transcribing, progress, msg),
        loop,
    )

transcript = await asyncio.to_thread(
    transcribe_audio, audio_path, language=..., ...,
    progress_cb=_asr_progress_cb,
)
```

注意：`update_progress` 在单例连接下线程安全（aiosqlite 内部队列串行化）。`run_coroutine_threadsafe` 将协程调度到事件循环线程执行。

`_transcribe_file`（单文件路径）也回调一次 100% 表示完成：`if progress_cb: progress_cb(1.0, "Transcription complete")`。

### D6: SSE 超时与心跳（R6）

`task_progress` 的 `event_generator` 修改：

```python
async def event_generator():
    start_time = asyncio.get_running_loop().time()
    MAX_DURATION = 30 * 60  # 30 分钟
    HEARTBEAT_INTERVAL = 15

    while True:
        now = asyncio.get_running_loop().time()
        if now - start_time > MAX_DURATION:
            return  # 关闭连接，前端 reconnect

        task = await get_task(job_id)
        if not task:
            yield {"event": "progress", "data": json.dumps({"error": "Task not found"})}
            break

        data = {...}
        yield {"event": "progress", "data": json.dumps(data)}

        if task["stage"] in (complete, failed, cancelled):
            ...
            break

        # 心跳 + 等待（可被取消）
        try:
            await asyncio.wait_for(_heartbeat_sleep(), timeout=HEARTBEAT_INTERVAL)
        except asyncio.TimeoutError:
            yield {"event": "ping", "data": ""}
            continue
```

**简化实现**：用 `asyncio.sleep(1)` 每秒轮询，累计 15 秒发一次心跳。但每秒查 DB 仍是开销。**更好**：每秒检查终态但只在 15 秒间隔发心跳。权衡后采用：

```python
last_heartbeat = start_time
while True:
    task = await get_task(job_id)
    ...
    if terminal: yield complete; break
    elapsed = now - start_time
    if elapsed > MAX_DURATION:
        return  # 前端 reconnect
    if now - last_heartbeat >= HEARTBEAT_INTERVAL:
        yield {"event": "ping", "data": ""}
        last_heartbeat = now
    await asyncio.sleep(1)
```

**注意**：`ping` 事件前端的 parser 会忽略吗？sseParser 对 `event: "ping"` 会调用 `onMessage({event: "ping", data: ""})`，但 `dataLines.length` 为 0 不 dispatch——**验证**：dispatch 在 `dataLines.length > 0` 时才调用 onMessage，`data: ""` 会 push 空字符串到 dataLines（`dataLines.push("")`），length 变为 1，会 dispatch。**所以 `ping` 事件会触发前端 onMessage**。但 useSSE 只处理 `progress` 和 `complete`，`ping` 会被忽略。

**更安全**：用 SSE 注释行而非 event。sse_starlette 的 yield 格式：注释行是 `": keepalive\n\n"`。但 sse_starlette 的 EventSourceResponse 会把 dict 包装。直接 yield 字符串？查 sse_starlette 文档——**最安全**：yield `{"data": "", "event": "ping"}` 前端忽略未知事件。或直接每 15 秒不 yield 心跳，只靠 `asyncio.sleep(1)` 轮询保持连接 alive——SSE 连接只要服务端不关闭就保持。**但** nginx/代理可能因无数据超时断开。**最终决策**：yield `{"event": "ping", "data": ""}`，前端忽略。前端无需改动。

### D7: yt-dlp 错误分类（R7）

`subtitle.py` 新增：

```python
def classify_ytdlp_error(exc: Exception) -> str:
    """Map a yt-dlp / download exception to a stable error code."""
    msg = str(exc).lower()
    # 明确的 yt-dlp DownloadError
    if "private" in msg or "login required" in msg:
        return "VIDEO_PRIVATE"
    if "geo" in msg or "not available in your country" in msg or "region" in msg:
        return "VIDEO_GEO_RESTRICTED"
    if "404" in msg or "not found" in msg or "unavailable" in msg or "deleted" in msg:
        return "VIDEO_NOT_FOUND"
    if "cookie" in msg or "login" in msg and "required" in msg:
        return "VIDEO_COOKIE_INVALID"
    return "VIDEO_FETCH_FAILED"
```

`get_video_info` 改造：异常时 attach code 到 exception 或抛自定义异常。**最简**：`get_video_info` 保持原样（捕获所有异常返回 None），但在 `routes.py` 的 try 中对 `get_video_info` 失败再做分类——**但 `get_video_info` 返回 None 而非抛异常**。看代码：`get_video_info` 内部 except 返回 `{"title": None, "thumbnail_url": None}`，不抛异常。

**设计调整**：让 `get_video_info` 在失败时抛异常而非静默返回 None，这样 `routes.py` 能分类。或：保持 `get_video_info` 静默，由 `routes.py` 检查 `title is None` 后重跑一次 `extract_info` 获取异常。

**最终方案**：新增 `get_video_info_strict(url, ...) -> dict` 抛异常版本；`get_video_info` 保持兼容（其他调用方）；`routes.py` 用 strict 版本。

```python
def get_video_info_strict(url: str, *, cookiefile_path=None) -> dict:
    """Like get_video_info but raises on failure with classified code."""
    ydl_opts = _ydl_opts(cookiefile_path=cookiefile_path)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise RuntimeError("yt-dlp returned no info")
            return {"title": info.get("title"), "thumbnail_url": info.get("thumbnail")}
    except Exception as e:
        code = classify_ytdlp_error(e)
        err = RuntimeError(f"{code}: {e}")
        err.code = code
        raise err from e
```

`routes.py` 捕获后：`code = getattr(e, "code", "VIDEO_FETCH_FAILED")`。

### D8: LLM 重试（R8）

`note_gen.py` 新增重试逻辑：

```python
import time
from openai import APIError, APIConnectionError, APITimeoutError, RateLimitError, APIStatusError

def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500
    return False

# generate_notes 内部：
max_attempts = 3
for attempt in range(max_attempts):
    try:
        response = client.chat.completions.create(...)
        break
    except Exception as e:
        if attempt + 1 == max_attempts or not _is_retryable(e):
            raise
        wait = 2 ** (attempt + 1)  # 2s, 4s
        logger.warning(f"LLM call attempt {attempt+1} failed, retrying in {wait}s: {e}")
        time.sleep(wait)
```

### D9: 长转录分块生成（R9）

`note_gen.py` 新增分块逻辑：

```python
def _split_transcript(transcript: str, max_chars: int = MAX_TRANSCRIPT_CHARS) -> list[str]:
    """Split transcript at timestamp-line boundaries, each chunk <= max_chars."""
    if len(transcript) <= max_chars:
        return [transcript]
    lines = transcript.split("\n")
    chunks = []
    current = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1  # +1 for \n
        if current_len + line_len > max_chars and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks

def generate_notes(transcript, ..., has_timestamps=True):
    chunks = _split_transcript(transcript)
    if len(chunks) == 1:
        return _generate_notes_single(chunks[0], ...)  # 原有逻辑

    # 多块：每块生成子笔记
    sub_notes = []
    for i, chunk in enumerate(chunks):
        logger.info(f"Generating notes for chunk {i+1}/{len(chunks)}")
        sub_notes.append(_generate_notes_single(chunk, ..., has_timestamps=has_timestamps))

    # 合并：标题层级整合
    merged = _merge_notes(sub_notes, video_title, language, ...)
    return normalize_note_markdown(merged)


def _merge_notes(sub_notes, video_title, language, ...):
    """Merge sub-notes by unifying heading hierarchy + adding overview."""
    # 拼接后调一次 LLM 做整合
    combined = "\n\n---\n\n".join(sub_notes)
    # prompt：整合标题层级，去重，加总览
    ...
```

**注意**：`generate_notes` 被调用时 `has_timestamps` 对所有 chunk 一致。分块不改变时间戳格式。

### D10: DB 单例连接（R10）

`db.py` 改造：

```python
_db_conn: aiosqlite.Connection | None = None

async def _get_db() -> aiosqlite.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = await aiosqlite.connect(str(DB_PATH))
        await _db_conn.execute("PRAGMA foreign_keys = ON")
        _db_conn.row_factory = aiosqlite.Row
    return _db_conn

async def init_db() -> None:
    global _db_conn
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _db_conn = await aiosqlite.connect(str(DB_PATH))
    await _db_conn.execute("PRAGMA journal_mode=WAL")
    await _db_conn.execute("PRAGMA foreign_keys = ON")
    _db_conn.row_factory = aiosqlite.Row
    try:
        await _db_conn.executescript(_CREATE_TABLE_SQL)
        # ... migrations ...
        await _db_conn.commit()
    except Exception:
        await _db_conn.close()
        _db_conn = None
        raise
    await _cleanup_expired_tokens()

async def close_db() -> None:
    global _db_conn
    if _db_conn is not None:
        await _db_conn.close()
        _db_conn = None
```

**所有函数移除 `finally: await db.close()`**：改为 `db = await _get_db()` 直接使用。aiosqlite 单连接内部用队列串行化所有操作，线程安全。

`main.py` lifespan finally 中 `await close_db()`。

**风险**：单连接下长查询会阻塞其他操作。但本项目查询都很快（单行 CRUD），WAL 模式读写不互斥，风险低。

### D11: 进度数值统一（R11）

字幕路径 `_process_video_url`：
- `0.1 fetching_info`（不变）
- `0.2 extracting_subtitles`（原 0.1）
- `0.5 subtitles found`（原 0.5，保留，语义为"转录完成"与 ASR 路径 0.6 对齐）
- `0.7 generating`（不变）
- `0.9 generated`（不变）

ASR 路径 `_process_video_url`：
- `0.1 fetching_info`（不变）
- `0.2 no_subs downloading`（原 0.2）
- `0.3 downloading`（原 0.2，不变）
- `0.4-0.6 transcribing`（ASR 进度回调 0.4+fraction*0.2）
- `0.6 transcription complete`（原 0.6，不变）
- `0.7 generating`（不变）
- `0.9 generated`（不变）

**最小改动**：字幕路径的 `0.1` 调整为 `0.2`（与 ASR 的 `0.2 no_subs` 对齐语义：信息获取完成进入转录阶段）。

## 跨层影响

### 前端改动（最小）

1. `api/client.ts`：`TASK_MESSAGE_ERROR_CODES` set 增加：
   ```ts
   "VIDEO_PRIVATE",
   "VIDEO_GEO_RESTRICTED",
   "VIDEO_NOT_FOUND",
   "VIDEO_COOKIE_INVALID",
   ```
2. `i18n/locales/en.json` errors 对象增加：
   ```json
   "videoPrivate": "...",
   "videoGeoRestricted": "...",
   "videoNotFound": "...",
   "videoCookieInvalid": "..."
   ```
3. `i18n/locales/zh-CN.json` 同上中文翻译。

SSE timeout / heartbeat、进度数值变化：前端无需改动（已兼容）。

## 回滚点

- R10 单例连接是最大改动。若出问题，回滚 `_get_db` 为每次新建连接 + 恢复各函数 `finally: close()`。
- R9 分块生成若 LLM 调用失败率升高，可回退为截断 + 提示（保留 `_split_transcript` 但合并失败时 fallback）。