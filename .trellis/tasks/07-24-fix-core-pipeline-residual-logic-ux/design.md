# Technical Design

## 架构概览

本次修复跨前后端 11 项，按模块分组如下：

| 组 | 涉及文件 | 修复项 |
|---|---|---|
| A. URL 进度与 info 复用 | `services/subtitle.py`, `services/audio.py`, `api/routes.py` | R1, R2, R3 |
| B. 终端态清理 | `db.py`, `main.py`, `frontend/HistoryPage.tsx` | R4, R5 |
| C. SSE 取结果失败 | `hooks/useSSE.ts` | R6 |
| D. DB 事务锁 | `db.py` | R7 |
| E. provider 校验 | `api/routes.py` | R8 |
| F. retry platform | `api/routes.py` | R9 |
| G. 搜索转义 | `db.py` | R10 |
| H. 死代码清理 | `services/subtitle.py`, `services/audio.py` | R11 |

---

## 组 A：URL 进度反馈 + yt-dlp info 复用 + 取消响应

### A.1 进度反馈（R1）

`_process_video_url` 在 `get_video_info_strict` 之前插入一条进度：

```python
await update_progress(job_id, TaskStage.downloading, 0.02, "Fetching video info...")
```

- 复用 `TaskStage.downloading`（不新增 stage 枚举），progress=0.02 表示刚开始。
- `StepIndicator.getStepStatuses` 现有逻辑：`stage === "downloading"` → `["active", "pending", "pending"]`，已满足显示 spinner 的需求。
- `TaskStage.downloading` 在 URL 链路原本用于"无字幕下载音频 0.15"，现在提前到 0.02 复用，语义为"下载/获取阶段"，不冲突。

### A.2 yt-dlp info 复用（R2）

**核心思路**：`get_video_info_strict` 调用 `ydl.extract_info(url, download=False)` 一次，把返回的 `info` dict 透传给后续 `extract_subtitles` 和 `download_audio_via_ytdlp`，后者改用 `ydl.process_ie_result(info, download=True)` 代替 `ydl.download([url])`，跳过二次 `extract_info`。

**改动**：

1. `get_video_info_strict` 返回值增加 `info` 字段：
   ```python
   return {"title": info.get("title"), "thumbnail_url": info.get("thumbnail"), "info": info}
   ```

2. `extract_subtitles` 增加 `info: dict | None = None` 参数：
   ```python
   def extract_subtitles(url, languages=None, *, cookiefile_path=None,
                         cancel_event=None, info=None):
       with yt_dlp.YoutubeDL(ydl_opts) as ydl:
           if info is not None:
               ydl.process_ie_result(info, download=True)
           else:
               ydl.download([url])
   ```
   - `skip_download=True` 在 opts 中，`process_ie_result` 不会下载视频文件，只写字幕。
   - 当传入 info 时，`url` 参数不再用于 extract，仅作 fallback 日志。

3. `download_audio_via_ytdlp` 增加 `info: dict | None = None` 参数：
   ```python
   def download_audio_via_ytdlp(url, output_dir, *, cookiefile_path=None,
                                cancel_event=None, info=None):
       with yt_dlp.YoutubeDL(ydl_opts) as ydl:
           if info is not None:
               ydl.process_ie_result(info, download=True)
           else:
               ydl.download([url])
   ```
   - `format=bestaudio/best` 在 opts 中，`process_ie_result` 会按 format 下载音频。

4. `_process_video_url` 把 `video_info["info"]` 传给后续两个调用：
   ```python
   video_info = await asyncio.to_thread(get_video_info_strict, url, ...)
   info = video_info.get("info")
   ...
   subtitle_text = await asyncio.to_thread(extract_subtitles, url, ..., info=info)
   ...
   audio_path = await asyncio.to_thread(download_audio_via_ytdlp, url, tmpdir, ..., info=info)
   ```

**风险**：`process_ie_result` 是 yt-dlp 内部 API，不如 `download([url])` 稳定。需测试字幕和音频下载在传入 info 后正常工作。若 `process_ie_result` 行为不符预期，退化为保留 `download([url])` 但接受 info 参数（此时 R2 不成立，需回退到保守方案，仅 cleanup 死代码）。

**兼容性**：`info` 参数默认 None，不影响其他调用方（测试中 mock）。

### A.3 取消在 extract_info 阶段可响应（R3）

yt-dlp 的 `progress_hooks` 只在下载时触发，`extract_info` 阻塞期间无法取消。采用**超时轮询**方案：

`get_video_info_strict`、`extract_subtitles`、`download_audio_via_ytdlp` 中，对 `extract_info` / `download` 的 `asyncio.to_thread` 调用，在 routes 层用 `asyncio.wait_for` + 周期检查 `cancel_event` 包装：

```python
async def _run_with_cancel_check(coro_factory, cancel_event, interval=2.0):
    """在 to_thread 包装的阻塞调用期间周期检查 cancel_event。"""
    while True:
        task = asyncio.create_task(coro_factory())
        try:
            return await asyncio.wait_for(task, timeout=interval)
        except asyncio.TimeoutError:
            if cancel_event and cancel_event.is_set():
                task.cancel()
                raise asyncio.CancelledError()
            # 继续等待
            return await task
```

**简化方案**（更稳健）：`asyncio.to_thread` 返回的 future 无法中断底层线程，但 `task.cancel()` 会向 asyncio 任务发 CancelledError。线程仍在跑，但 routes 层 catch 后能继续走 cancelled 分支。代价是线程泄漏（yt-dlp 跑完才回收），但逻辑上取消生效。采用此简化方案：

```python
# routes.py _process_video_url 中
try:
    video_info = await asyncio.to_thread(get_video_info_strict, url, ...)
    await _cancellation_checkpoint(job_id)
except asyncio.CancelledError:
    raise
except Exception as e:
    if cancel_event is not None and cancel_event.is_set():
        await update_progress(job_id, TaskStage.cancelled, 0.0, "Cancelled")
        return
    ...
```

实际上现有代码已有 `cancel_event` 检查点（`_cancellation_checkpoint` 在每个阶段后）。问题在于 `extract_info` 本身阻塞期间无法检查。真正能做的是在 **service 层**用 `cancel_event` 周期检查：

`get_video_info_strict` 内部，把 `extract_info` 拆成"提取 + processing hook 检查"：

```python
def get_video_info_strict(url, *, cookiefile_path=None, cancel_event=None):
    ydl_opts = _ydl_opts(cookiefile_path=cookiefile_path)
    # 添加 progress_hooks 做 cancel 检查（extract_info 也会触发部分 hook）
    if cancel_event is not None:
        def _cancel_hook(d):
            if cancel_event.is_set():
                raise yt_dlp.utils.DownloadCancelled("Cancelled by user")
        ydl_opts.setdefault("progress_hooks", []).append(_cancel_hook)
    ...
```

但 `extract_info(download=False)` 是否触发 `progress_hooks`？经查 yt-dlp 源码，`progress_hooks` 只在下载阶段触发，`extract_info(download=False)` 不触发。所以 hook 方案对 extract_info 无效。

**最终方案**：在 routes 层对 `get_video_info_strict` 的 `asyncio.to_thread` 调用用 `asyncio.wait_for` 做软超时 + cancel_event 检查循环。线程虽不能强行中断，但逻辑上取消能及时响应：

```python
async def _to_thread_with_cancel(func, *args, cancel_event=None, timeout=3.0, **kwargs):
    """运行 to_thread，每 timeout 秒检查一次 cancel_event。被取消时向 asyncio 任务发取消。"""
    while True:
        fut = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
        done, _ = await asyncio.wait({fut}, timeout=timeout)
        if fut in done:
            return fut.result()
        if cancel_event is not None and cancel_event.is_set():
            fut.cancel()
            raise asyncio.CancelledError()
```

routes 层把 `get_video_info_strict`、`extract_subtitles`、`download_audio_via_ytdlp` 的 `asyncio.to_thread` 调用替换为 `_to_thread_with_cancel(...)`。

**取舍**：`fut.cancel()` 只取消 asyncio 端，底层线程继续跑到 yt-dlp 返回（被 GC 回收）。可接受，因为 routes 层已走 cancelled 分支，用户看到取消生效。

### A.4 死代码清理（R11）

- 删除 `get_video_title`（无调用方，grep 确认）。
- 删除 `get_video_info`（非 strict 无调用方，`test_pipeline_bugs.py` 中 `fake_get_video_info` mock 的是 `routes.get_video_info_strict`，不引用）。
- `download_audio_via_ytdlp`：删除 `if downloaded.endswith(".wav"): return downloaded` 分支（`format=bestaudio/best` 不产出 .wav）。始终走 `extract_audio` 转 wav。**注意**：若 A.2 用 `process_ie_result`，产出文件名可能不同，需测试确认。

---

## 组 B：终端态清理

### B.1 后端自动清理（R4）

`db.py` 新增：

```python
TERMINAL_STAGES = (TaskStage.complete.value, TaskStage.failed.value, TaskStage.cancelled.value)

async def cleanup_old_terminal_tasks(max_age_days: int = 30) -> int:
    """删除超过 max_age_days 天的 terminal 任务行及其 input 文件。返回删除行数。"""
    cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
    db = await _get_db()
    cursor = await db.execute(
        "SELECT job_id, input_file_path FROM tasks "
        "WHERE stage IN (?, ?, ?) AND created_at < ? AND input_file_path IS NOT NULL",
        (*TERMINAL_STAGES, cutoff),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    upload_root = UPLOAD_DIR.resolve()
    for row in rows:
        if row["input_file_path"]:
            p = Path(row["input_file_path"]).resolve()
            if upload_root in p.parents:
                p.unlink(missing_ok=True)
    cursor = await db.execute(
        "DELETE FROM tasks WHERE stage IN (?, ?, ?) AND created_at < ?",
        (*TERMINAL_STAGES, cutoff),
    )
    # note_tags 由 FK ON DELETE CASCADE 自动删除
    await db.commit()
    return cursor.rowcount
```

`main.py` lifespan startup 调用：

```python
cleaned = await cleanup_old_terminal_tasks()
if cleaned:
    logger.info("Cleaned up %d old terminal tasks", cleaned)
```

- `note_tags` 有 `ON DELETE CASCADE`，删 task 行自动清关联。
- `cleanup_failed_task_files`（7 天）保留不动，两者职责互补。

### B.2 前端隐藏 cancelled（R5）

`HistoryPage.tsx`：
- 增加 `showCancelled` state（默认 false）。
- 在获取列表后、渲染前，若 `!showCancelled` 则过滤掉 `stage === "cancelled"` 的项。
- **注意**：过滤应在前端做，不影响分页 API 调用（否则后端需改）。但后端分页 + 前端过滤会导致每页数量不一致。**权衡**：后端 list_tasks 增加可选参数 `exclude_cancelled: bool`，默认 false，前端 HistoryPage 传 `exclude_cancelled=true`，开关打开时不传。这样分页计数正确。

  实现：`list_tasks` 增 `exclude_cancelled: bool = False` 参数，传给 `get_user_tasks`/`count_user_tasks`。SQL 条件 `conditions.append("t.stage != ?")` (`TaskStage.cancelled.value`)。

---

## 组 C：useSSE 取结果失败处理（R6）

`useSSE.ts` 重连逻辑中，`fetchTaskById` 返回 `complete` 后调 `fetchResult`：

```typescript
if (task.stage === "complete") {
  try {
    const note = await fetchResult(jobId);
    if (abortController.signal.aborted) return;
    setResult(note.markdown);
    setError(null);
    return;
  } catch (e) {
    if (abortController.signal.aborted) return;
    // 区分 4xx 与 5xx/网络
    if (e instanceof ApiError && e.code === "TASK_STILL_PROCESSING") {
      // 罕见：SSE 说 complete 但 REST 说 processing，重连
    } else if (e instanceof ApiError && /^[4]\d\d$/.test(/* status */)) {
      // 4xx 确定性失败，不重试
      setError(/* 取结果失败文案 */);
      return;
    }
    // 5xx / 网络错误：落入下方重连
  }
}
```

简化：`fetchResult` 已抛 `ApiError`。判断：
- `ApiError.code === "TASK_STILL_PROCESSING"` → 重连（极少发生）。
- 其他 `ApiError`（含 4xx/5xx）→ `setError`，`return` 终止。
- 非 `ApiError`（网络 TypeError）→ 落入重连。

实现：

```typescript
if (task.stage === "complete") {
  try {
    const note = await fetchResult(jobId);
    if (abortController.signal.aborted) return;
    setResult(note.markdown);
    setError(null);
    return;
  } catch (e) {
    if (abortController.signal.aborted) return;
    if (e instanceof ApiError && e.code !== "TASK_STILL_PROCESSING") {
      setError(e.message || t("errors.fetchResultFailed"));
      return;
    }
    // TASK_STILL_PROCESSING 或网络错误：落入重连
  }
}
```

- `TASK_STILL_PROCESSING` 时 task 不是 complete，逻辑走不到这（fetchTaskById 返回的 stage 才进 complete 分支）。但为防御性保留。
- 非网络 4xx 必须终止，不消耗重连次数。

### i18n

新增 `errors.fetchResultFailed` 到 en/zh-CN locale。

---

## 组 D：DB 事务并发锁（R7）

`db.py` 模块级：

```python
import asyncio
_tag_write_lock = asyncio.Lock()
```

`add_tags_to_note` 和 `batch_add_tag` 的 `BEGIN IMMEDIATE ... commit/rollback` 块用 `async with _tag_write_lock:` 包裹：

```python
async def add_tags_to_note(job_id, user_id, tag_ids):
    unique_ids = list(dict.fromkeys(tag_ids))
    if not unique_ids:
        return True
    async with _tag_write_lock:
        db = await _get_db()
        await db.execute("BEGIN IMMEDIATE")
        try:
            ...
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            raise
```

- 仅保护这两个显式事务函数。`update_progress` 等其他操作不受影响（自动 commit，aiosqlite 串行化）。
- `remove_tag_from_note`、`get_tags_for_note` 等短操作不加锁。

---

## 组 E：provider 配置校验（R8）

`_resolve_providers` 已返回 `ProviderBundle`。`_ensure_providers_configured` 增加校验：

```python
async def _ensure_providers_configured(user_id: str | None) -> str | None:
    providers = await _resolve_providers(user_id)
    if not providers.asr_api_key or not providers.llm_api_key:
        return "PROVIDER_NOT_CONFIGURED"
    if not providers.asr_api_base or not providers.asr_model:
        return "PROVIDER_NOT_CONFIGURED"
    if not providers.llm_api_base or not providers.llm_model:
        return "PROVIDER_NOT_CONFIGURED"
    return None
```

- env 默认 `ASR_API_BASE`/`LLM_API_BASE`/`ASR_MODEL`/`LLM_MODEL` 若为空字符串，用户未配置时校验失败。
- 复用 `PROVIDER_NOT_CONFIGURED` 错误码，前端已能处理。

---

## 组 F：retry platform（R9）

`routes.py retry_task` upload 分支：

```python
return ProcessResponse(
    job_id=new_job_id,
    title="",
    thumbnail_url="",
    platform="",  # 改 "upload" → ""
    source_type="upload",
)
```

- 空字符串前端 `VideoInfoCard` 的 `platformInfo = platform ? PLATFORM_STYLES[...] : undefined` → `""` 为 falsy，`platformInfo` 为 undefined，不渲染 badge，正确。

---

## 组 G：搜索 LIKE 转义（R10）

`db.py` 新增 helper：

```python
def _escape_like(value: str) -> str:
    """转义 LIKE 模式中的 % 和 _，并在首尾加 %。"""
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
```

`get_user_tasks` 和 `count_user_tasks` 中：

```python
if search is not None:
    like = _escape_like(search)
    conditions.append(
        "(t.message LIKE ? ESCAPE '\\' OR ... )"
    )
    params.extend([like, like, like, like])
```

- 用 `ESCAPE '\\'` 声明转义字符。

---

## 组 H：其他

### 死代码清理（R11）

- 删除 `subtitle.py` 中 `get_video_title`、`get_video_info`（非 strict）。
- `audio.py` `download_audio_via_ytdlp` 删除 `.wav` 死分支。
- 测试 `test_pipeline_bugs.py` 中 `fake_get_video_info` 需检查是否引用被删函数（grep 确认是 mock routes.get_video_info_strict，不受影响，但函数名要检查）。

---

## 测试策略

- **后端**：
  - `test_pipeline_bugs.py` / `test_core_reliability.py` / `test_pipeline_logic_ux.py` 现有测试须通过。
  - 新增：info 复用测试（mock yt-dlp，断言 `extract_info` 只调一次）。
  - 新增：`_escape_like` 单元测试。
  - 新增：`cleanup_old_terminal_tasks` 测试。
  - 新增：`_ensure_providers_configured` model/api_base 空校验测试。
- **前端**：
  - `useSSE.test.ts` 新增：complete + fetchResult 4xx → setError。
  - `HistoryPage` 新增：cancelled 任务默认隐藏 + 开关。
- 回归：`ruff check .` / `eslint .` / `vite build` / 前后端 test 全绿。