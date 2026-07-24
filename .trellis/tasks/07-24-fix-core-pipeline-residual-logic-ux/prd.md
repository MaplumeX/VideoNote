# Fix core pipeline residual logic and UX issues

## Goal

修复核心链路（提交 → 视频信息 → 字幕/ASR → 笔记生成 → SSE 进度 → 取消/恢复/重试）中剩余的逻辑 bug、可靠性隐患与体验问题，共 11 项。

## Scope

前后端跨层。后端：`app/api/routes.py`、`app/services/{subtitle,audio,transcribe,note_gen,markdown}.py`、`app/db.py`、`app/task_runner.py`、`app/main.py`。前端：`src/hooks/useSSE.ts`、`src/pages/NewNotePage.tsx`、`src/components/StepIndicator.tsx`、`src/pages/HistoryPage.tsx`、`src/types/index.ts`、i18n。

## Requirements

### R1. URL 链路「视频信息抓取」阶段有进度反馈
- 创建 task 后、首次 `get_video_info_strict` 之前，立即写一条进度，stage 非 `pending`，message 表达"正在获取视频信息"。
- 前端 `StepIndicator` 在该阶段把 step1 显示为 active（spinner），而非三个空心圆。
- 文案不能误导为"排队"。

### R2. URL 链路合并 yt-dlp `extract_info` 调用
- 同一 URL 在一次任务内 `extract_info(url, download=False)` 最多调用 1 次。
- `get_video_info_strict` 抓取的 `info` dict 须在阶段间复用：`extract_subtitles` 与 `download_audio_via_ytdlp` 接收已抓取的 info，跳过二次 `extract_info`。
- 不改变对外行为：字幕仍按语言优先级选择，音频仍下载为可 ASR 的格式。

### R3. 取消在 yt-dlp `extract_info` 阶段可响应
- `get_video_info_strict`、`extract_subtitles`、`download_audio_via_ytdlp` 在 `extract_info`/字幕提取/下载的阻塞期间，周期性检查 `cancel_event`，被取消时及时退出（抛 `DownloadCancelled` 或 `RuntimeError("cancelled")`），不再等到下一个 progress_hook 触发。

### R4. 终端态任务自动清理
- 后端在启动时（lifespan）执行一次清理：删除超过 30 天的 terminal（complete/failed/cancelled）任务行（含关联 note_tags），先删其 input 文件再删行。
- 后续周期性清理（可选，非阻塞）：若实现简单则加，否则仅启动清理。

### R5. 前端历史页默认隐藏 cancelled 任务
- `HistoryPage` 默认不显示 `stage === "cancelled"` 的任务。
- 提供"显示已取消"开关（checkbox / toggle），开启后显示全部。
- 状态保留在组件本地 state（不持久化）。

### R6. useSSE 在「任务已完成但取结果失败」时正确提示
- SSE 流断 → `fetchTaskById` 返回 `complete` → `fetchResult` 抛错时，`useSSE` 不应退化为重连循环，而应 `setError` 明确提示"取结果失败"并终止。
- 区分网络抖动（可重试）与确定性失败（4xx 返回）：仅对 5xx / 网络错误重连上限次，4xx 直接报错。

### R7. DB 显式事务加并发锁
- `add_tags_to_note`、`batch_add_tag` 的 `BEGIN IMMEDIATE` 事务块用 `asyncio.Lock` 保护，防止事务期间被其他协程（如 SSE 每秒 `update_progress`）的非事务写插入导致 "cannot start a transaction within a transaction"。
- 锁粒度最小：仅包裹显式事务函数；其他操作不受影响。

### R8. provider 配置校验 model/api_base 非空
- `_ensure_providers_configured` 除校验 `api_key` 外，还校验 `asr_model`/`llm_model` 与 `asr_api_base`/`llm_api_base` 非空（用户配置或 env 默认）。
- 缺失时返回 422 `PROVIDER_NOT_CONFIGURED`（复用现有错误码）。
- env python 自身（`ASR_API_BASE`/`LLM_API_BASE`）默认值若本就为空字符串，维持现状，仅在用户未填时由 env 兜底逻辑不变；只要最终解析值为空就拒绝。

### R9. retry upload 不再写 `platform="upload"`
- `retry_task` upload 分支返回的 `ProcessResponse` 不使用语义错误的 `platform="upload"`；upload 来源的 platform 应留空或为 `None`，前端 `VideoInfoCard` 已能处理无 platform 情况。

### R10. 搜索 LIKE 转义 `%`/`_`
- `count_user_tasks` / `get_user_tasks` 的 `search` 参数在使用前转义用户输入的 `%` 与 `_` 字符，避免误匹配。仍用 `LIKE` 实现。

### R11. 清理死代码
- 删除 `get_video_title`、`get_video_info`（非 strict 版）等无调用方函数（若确认 R2 重构后仍无引用）。
- 移除 `download_audio_via_ytdlp` 中 `if downloaded.endswith(".wav")` 死分支（若确认 yt-dlp `format=bestaudio/best` 不产出 .wav）—— 改为始终转 wav，保持一致。

## Out of Scope

- #4 SSE 30 分钟硬断长视频体验优化（逻辑能恢复，暂不改）。
- #6 上传视频 ffmpeg 抽首帧缩略图（Q3=A 保持现状，不增强）。
- #8 `_get_db` 懒初始化竞态（启动 `init_db()` 已赋值，正常路径走不到，暂不处理）。
- #9 崩溃恢复重头跑 ASR（持久化中间 transcript 属架构性增强，不在本次范围）。

## Acceptance Criteria

- [ ] AC1: 提交 URL 后，SSE 立即推送一条非 `pending` stage 的进度，`StepIndicator` step1 显示 spinner。
- [ ] AC2: 单次 URL 任务内 `extract_info(download=False)` 仅调用一次；字幕提取与音频下载复用抓取的 info。
- [ ] AC3: 在 `extract_info` 阻塞期间（长视频元数据获取）用户取消，能在数秒内（非等到下载阶段）生效，任务 stage 转为 `cancelled`。
- [ ] AC4: 启动时自动删除 30 天以上 terminal 任务行；关联 `note_tags` 一并删除；input 文件先删除。
- [ ] AC5: `HistoryPage` 默认不显示 cancelled 任务；开关开启后显示全部；分页计数正确。
- [ ] AC6: 任务 complete 后 `fetchResult` 网络失败，`useSSE` 不进入重连循环，直接 `setError` 终止；4xx 不重试，5xx/网络错误重试上限次。
- [ ] AC7: `add_tags_to_note`/`batch_add_tag` 事务期间并发 `update_progress` 不报 "cannot start a transaction within a transaction"。
- [ ] AC8: `_ensure_providers_configured` 在 model 或 api_base 为空时返回 422。
- [ ] AC9: retry upload 的 `ProcessResponse.platform` 不为 `"upload"`。
- [ ] AC10: 搜索含 `a_b` 的关键词不误匹配 `aXb`；含 `%` 当普通字符处理。
- [ ] AC11: 删除无调用方的 `get_video_title`/`get_video_info`（非 strict）后测试仍通过。
- [ ] AC12: 后端 `uv run pytest -q` 全绿；前端 `npm test -- --run` 全绿；`ruff check .` / `eslint .` clean；`vite build` OK。