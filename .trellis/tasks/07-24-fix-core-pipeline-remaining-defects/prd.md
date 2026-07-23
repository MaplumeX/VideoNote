# 修复核心链路剩余逻辑缺陷与体验问题

## Goal

修复视频笔记生成核心链路（提交 → 字幕/ASR → 笔记生成 → SSE 进度 → 笔记管理）中已识别的 11 项逻辑缺陷与体验问题，覆盖正确性、资源清理、错误反馈、性能四个维度。

## Background

前两轮已修正字幕时间戳、ASR chunk 偏移、标题同步等问题。本轮聚焦剩余的：字幕语言不匹配、缩略图拖垮任务、失败文件残留、大文件 ASR 切分脆弱、SSE 连接泄漏、进度卡顿、错误信息笼统、LLM 无重试、长转录截断、DB 频繁建连、进度刻度跳跃。

## Requirements

### R1 字幕语言与用户选择一致

- 调用 `extract_subtitles` 时按用户提交的 `language` 重排字幕语言优先级：`zh-CN` → `["zh-Hans","zh","en","ja"]`；`en` → `["en","zh-Hans","zh","ja"]`。
- 不改变 `extract_subtitles` 的服务层签名（已支持 `languages` 形参）。

### R2 缩略图下载失败不拖垮任务

- `get_video_info` 与 `download_thumbnail` 拆为独立 try 块。
- `get_video_info` 失败 → 任务失败 `VIDEO_FETCH_FAILED`。
- `download_thumbnail` 失败 → 仅置空缩略图，任务继续。

### R3 失败任务源文件定时清理

- 不在 `_process_video_file` finally 中删除 failed 任务源文件（保留 retry 能力）。
- 应用启动时清理 `stage='failed' AND created_at < now - 7d` 的任务的 `input_file_path` 文件，并置空 DB 字段。
- 清理函数在 `lifespan` 中 `recover_incomplete_tasks` 之后执行。

### R4 大文件 ASR 切分健壮化

- `_transcribe_large_file` 检查 ffprobe `returncode`，失败抛带语义的异常。
- `chunk_duration` 设最小下限 30 秒，避免碎块爆炸。
- `total_seconds` 解析前判空。

### R5 大文件 ASR 进度回报

- `transcribe_audio` / `_transcribe_large_file` / `_transcribe_file` 增加可选 `progress_cb: Callable[[float, str], None] | None` 参数。
- 每个 chunk 完成后回调当前阶段进度（映射到 ASR 阶段 0.4–0.6 区间）。
- 回调在线程中执行，通过 `asyncio.run_coroutine_threadsafe` 调度到事件循环写 DB。

### R6 SSE 超时与心跳

- SSE `event_generator` 加最大轮询时长 30 分钟，超时后关闭连接（前端已有 reconnect 机制自动接管）。
- 每 15 秒发送一次 SSE 注释行 `: keepalive`（前端 sseParser 已忽略 `:` 开头的行）。
- 不新增 SSE 事件类型，前端无需改动。

### R7 细化视频获取错误

- 新增 `classify_ytdlp_error(exc) -> str` helper（放在 `services/subtitle.py` 或 `errors.py`），按 yt-dlp 异常特征映射到细分错误码：
  - `VIDEO_PRIVATE`：私有视频 / 需登录
  - `VIDEO_GEO_RESTRICTED`：地区限制
  - `VIDEO_NOT_FOUND`：视频不存在 / 已删除
  - `VIDEO_COOKIE_INVALID`：cookie 过期或无效
  - `VIDEO_FETCH_FAILED`：其他（兜底）
- `get_video_info` 抛异常时附带分类后的 code；`routes.py` 捕获后用作 `update_progress` 的 message。
- 新增的错误码同步到前端 `TASK_MESSAGE_ERROR_CODES` set 和 `i18n locales`（en + zh-CN）。

### R8 LLM 调用重试

- `generate_notes` 对可重试异常（`RateLimitError`、`APITimeoutError`、`APIConnectionError`、5xx `APIStatusError`）做指数退避重试，最多 3 次，基础间隔 2s（2s/4s）。
- 4xx 不重试，直接抛出。
- 重试日志 `logger.warning` 记录次数与原因。

### R9 长转录分块生成

- 替换 `note_gen.py` 的 `transcript[:MAX_TRANSCRIPT_CHARS]` 截断逻辑。
- 按时间戳行分块，每块 ≤ `MAX_TRANSCRIPT_CHARS`（60000 字符），在段落边界切，不切断时间戳行。
- 每块调 `generate_notes` 生成子笔记。
- 拼接所有子笔记，再调一次 LLM 做标题层级整合（不重写正文，只统一标题层级与开篇总览）。
- 单块时（≤ MAX_TRANSCRIPT_CHARS）走原有一次生成路径，不额外调 LLM。

### R10 DB 单例连接

- `db.py` 改用应用级单例 aiosqlite 连接，`init_db` 初始化，`lifespan` 关闭。
- `_get_db` 返回共享连接，移除各函数的 `finally: await db.close()`。
- 保留 `PRAGMA foreign_keys = ON`、`journal_mode=WAL`。

### R11 进度数值统一单调

- 统一两条路径（字幕命中 / ASR 回退）的进度刻度：
  - 字幕路径：`0.1 fetching_info → 0.2 subtitles → 0.5 subtitles_ok → 0.7 generating → 0.9 generated → 1.0`
  - ASR 路径：`0.1 fetching_info → 0.2 no_subs → 0.3 downloading → 0.4-0.6 transcribing → 0.7 generating → 0.9 generated → 1.0`
- 字幕路径的 `0.5` 调整为 `0.5 subtitles found`（与 ASR 0.6 对齐语义：转录完成）。
- 前端只显示数值，不依赖具体语义，兼容。

## Acceptance Criteria

- [ ] AC1: 提交一个有英文自动字幕的中文视频，选 `zh-CN` 语言时优先使用中文字幕（若无中文字幕才回退英文）。
- [ ] AC2: 缩略图下载失败时任务不失败，正常生成笔记，缩略图为空。
- [ ] AC3: 构造一个失败超过 7 天且仍有 `input_file_path` 的 upload 任务，重启服务后文件被删除且 DB 字段置空。
- [ ] AC4: 不改变 retry 行为——failed 任务的源文件在 7 天内仍可用于 retry。
- [ ] AC5: 大音频文件（远超 ASR 上限）ASR 切分时 chunk 时长不低于 30 秒；ffprobe 失败时报 `TRANSCRIPTION_FAILED` 而非 `ValueError`。
- [ ] AC6: 大文件 ASR 期间 SSE 进度在 0.4–0.6 区间有阶段性更新（不再卡住）。
- [ ] AC7: SSE 连接超过 30 分钟自动关闭；前端自动重连。
- [ ] AC8: SSE 每 15 秒收到一次心跳（前端 sseParser 忽略，无副作用）。
- [ ] AC9: 私有视频链接报 `VIDEO_PRIVATE`；地区限制报 `VIDEO_GEO_RESTRICTED`；不存在视频报 `VIDEO_NOT_FOUND`；cookie 过期报 `VIDEO_COOKIE_INVALID`；其他报 `VIDEO_FETCH_FAILED`。
- [ ] AC10: LLM 遇 429/超时自动重试最多 3 次；4xx 不重试。
- [ ] AC11: 超过 60000 字符的转录文本不被截断丢失，生成完整笔记（分块 + 合并）。
- [ ] AC12: `_get_db` 不再每次新建连接；高频 SSE 轮询不产生连接风暴。
- [ ] AC13: 字幕路径与 ASR 路径进度数值单调且语义对齐。
- [ ] AC14: `ruff check .` 与 `pytest` 通过；前端 `npm run lint` 与 `npm run build` 通过。

## Out of Scope

- 不重构为连接池（本次用单例连接）。
- 不改前端 SSE 重连策略（已有，复用）。
- 不新增 API 端点。
- 不改数据库 schema。