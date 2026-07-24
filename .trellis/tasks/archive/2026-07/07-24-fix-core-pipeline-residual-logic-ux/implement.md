# Implementation Plan

## 执行顺序

按依赖与风险从低到高分阶段。每阶段结束跑测试验证。

---

## Phase 1: 低风险独立修复（R7, R8, R9, R10）

### 1.1 DB 事务并发锁（R7）
- [ ] `db.py` 模块级新增 `import asyncio` 和 `_tag_write_lock = asyncio.Lock()`
- [ ] `add_tags_to_note` 整个 `BEGIN IMMEDIATE ... commit/rollback` 块用 `async with _tag_write_lock:` 包裹
- [ ] `batch_add_tag` 同样包裹
- 验证：`uv run pytest tests/test_pipeline_bugs.py -q`

### 1.2 provider 配置校验（R8）
- [ ] `routes.py` `_ensure_providers_configured` 增加 `asr_api_base`/`asr_model`/`llm_api_base`/`llm_model` 空校验
- 验证：`uv run pytest tests/test_pipeline_logic_ux.py -q`

### 1.3 retry platform（R9）
- [ ] `routes.py retry_task` upload 分支 `platform="upload"` → `platform=""`
- 验证：`uv run pytest -q`

### 1.4 搜索 LIKE 转义（R10）
- [ ] `db.py` 新增 `_escape_like(value)` helper
- [ ] `get_user_tasks` 的 search 分支改用 `_escape_like` + `ESCAPE '\\'`
- [ ] `count_user_tasks` 同步修改
- [ ] 新增 `_escape_like` 单元测试
- 验证：`uv run pytest -q`

**Phase 1 Gate**：`ruff check . && uv run pytest -q` 全绿。

---

## Phase 2: 终端态清理（R4, R5）

### 2.1 后端自动清理（R4）
- [ ] `db.py` 新增 `cleanup_old_terminal_tasks(max_age_days=30)` 函数
- [ ] `main.py` lifespan startup 调用（在 `cleanup_failed_task_files` 之后）
- [ ] 新增测试：创建 31 天前 terminal 任务 → 清理后消失；非 terminal 保留
- 验证：`uv run pytest -q`

### 2.2 前端隐藏 cancelled + 后端 exclude_cancelled 参数（R5）
- [ ] `db.py` `get_user_tasks` / `count_user_tasks` 增 `exclude_cancelled: bool = False` 参数，SQL 条件 `t.stage != 'cancelled'`
- [ ] `routes.py` `list_tasks` 增 `exclude_cancelled: bool = False` query 参数并透传
- [ ] `frontend/src/api/client.ts` `fetchTasks` 增 `excludeCancelled?: boolean` 参数
- [ ] `frontend/src/pages/HistoryPage.tsx`：`showCancelled` state（默认 false），默认请求 `excludeCancelled=true`；toggle 开关切换
- [ ] i18n 新增 `history.showCancelled` / `history.hideCancelled` 文案
- [ ] 测试：前端 HistoryPage 渲染 cancelled 默认不显示 + 开关
- 验证：`uv run pytest -q && cd frontend && npm test -- --run`

**Phase 2 Gate**：前后端测试全绿，lint clean。

---

## Phase 3: useSSE 取结果失败处理（R6）

### 3.1 前端 useSSE 修复
- [ ] `useSSE.ts`：`fetchTaskById` 返回 complete 后 `fetchResult` 的 try/catch 中，`ApiError` 非 `TASK_STILL_PROCESSING` 时 `setError` + return 终止；非 ApiError（网络错误）落入重连
- [ ] i18n 新增 `errors.fetchResultFailed` 文案（en/zh-CN）
- [ ] `useSSE.test.ts` 新增测试：complete + fetchResult 抛 ApiError → setError，不重连
- 验证：`cd frontend && npm test -- --run`

**Phase 3 Gate**：前端测试全绿，eslint clean。

---

## Phase 4: URL 进度反馈 + yt-dlp info 复用 + 取消响应（R1, R2, R3）

### 4.1 进度反馈（R1）
- [ ] `routes.py _process_video_url`：在 `get_video_info_strict` 之前插入 `update_progress(job_id, TaskStage.downloading, 0.02, "Fetching video info...")`
- [ ] 消息本地化：service 层消息保持英文 code，前端翻译；此 message 是自由文案，前端 `translateTaskMessage` 不匹配 code 时原样返回 → 需用 i18n key 或保持英文。**决策**：用稳定文案 `"Fetching video info..."`，前端 `translateTaskMessage` 不命中 code → 原样展示。或加 i18n。
  - 简化：前端进度消息区已有 `progress.message` 直接展示，英文文案可接受。或用 `t("processing.fetchingVideoInfo")`。**选择**：后端 message 用英文 `"Fetching video info..."`，前端 i18n 增加翻译映射（在 `translateTaskMessage` 的 fallback 逻辑中处理不了自由文案，所以直接在 NewNotePage 展示时用 t() 映射）。**最终决策**：后端写稳定 code `FETCHING_VIDEO_INFO`，前端 `translateTaskMessage` 识别并翻译。
- 验证：`uv run pytest -q`

### 4.2 yt-dlp info 复用（R2）
- [ ] `subtitle.py` `get_video_info_strict` 返回值增 `info` 字段
- [ ] `subtitle.py` `extract_subtitles` 增 `info: dict | None = None` 参数，传入时用 `ydl.process_ie_result(info, download=True)` 代替 `ydl.download([url])`
- [ ] `audio.py` `download_audio_via_ytdlp` 增 `info: dict | None = None` 参数，同样替换
- [ ] `routes.py _process_video_url`：`video_info["info"]` 传给 `extract_subtitles` 和 `download_audio_via_ytdlp`
- [ ] 测试：mock yt-dlp，断言 `extract_info` 只调一次
- 验证：`uv run pytest -q`
- **风险标志**：若 `process_ie_result` 行为不符预期，回退为不传 info（保留 `download([url])`），仅完成 R1/R3，R2 降级。需手动或集成测试验证。

### 4.3 取消响应（R3）
- [ ] `routes.py` 新增 `_to_thread_with_cancel(func, *args, cancel_event, timeout=3.0, **kwargs)` helper
- [ ] `_process_video_url` 中 `get_video_info_strict`、`extract_subtitles`、`download_audio_via_ytdlp` 的 `asyncio.to_thread` 调用替换为 `_to_thread_with_cancel`
- [ ] 同样应用到 `_process_video_file` 的 `extract_audio`（已有 Popen 轮询，可保留原样或统一）
- [ ] 测试：模拟 cancel_event 在 to_thread 期间 set → 抛 CancelledError
- 验证：`uv run pytest -q`

**Phase 4 Gate**：后端测试全绿，ruff clean。手动验证：提交一个长视频，在"Fetching video info"阶段点取消，确认数秒内转为 cancelled。

---

## Phase 5: 死代码清理（R11）

### 5.1 删除无引用函数
- [ ] `subtitle.py` 删除 `get_video_title`（已 grep 确认无调用方）
- [ ] `subtitle.py` 删除 `get_video_info`（非 strict，无调用方）
- [ ] `audio.py` `download_audio_via_ytdlp` 删除 `if downloaded.endswith(".wav"): return downloaded` 死分支
- [ ] 检查 `routes.py` import 是否引用被删函数，清理 import
- [ ] 检查 `tests/test_pipeline_bugs.py` 的 `fake_get_video_info` mock 目标是否正确（mock 的是 `routes.get_video_info_strict`，不受影响）
- 验证：`uv run pytest -q && ruff check .`

**Phase 5 Gate**：测试全绿，ruff clean。

---

## Phase 6: 全量验证

### 6.1 后端
- [ ] `cd backend && uv run pytest -q` 全绿
- [ ] `cd backend && ruff check .` clean

### 6.2 前端
- [ ] `cd frontend && npm test -- --run` 全绿
- [ ] `cd frontend && npx eslint .` clean
- [ ] `cd frontend && npx vite build` OK

### 6.3 Spec 更新（Phase 3 规范）
- [ ] 更新 `.trellis/spec/backend/error-handling.md`：`FETCHING_VIDEO_INFO` code、`PROVIDER_NOT_CONFIGURED` 含 model/api_base 校验
- [ ] 更新 `.trellis/spec/backend/database-guidelines.md`：`_escape_like` 模式、`_tag_write_lock` 事务锁模式、`cleanup_old_terminal_tasks`
- [ ] 更新 `.trellis/spec/guides/cross-layer-thinking-guide.md`（如涉及）
- [ ] 更新前端 `TASK_MESSAGE_ERROR_CODES` 集合（增 `FETCHING_VIDEO_INFO`）

### 6.4 Commit
- [ ] `git add -A && git commit -m "fix(core): resolve 11 residual pipeline logic and UX issues"`

---

## 回滚点

- Phase 1-3 各自独立，可单独提交或回滚。
- Phase 4（R2 info 复用）是最高风险点。若 `process_ie_result` 有问题，Phase 4.2 可单独回退为不传 info，不影响 R1/R3。
- Phase 5 是纯删除，若有问题可直接 revert。