# 执行计划：修复核心链路剩余逻辑缺陷与体验问题

## 执行顺序

按依赖与风险排序：先改 db 基础设施（R10/R3），再改服务层（R4/R5/R7/R8/R9），再改路由层（R1/R2/R6/R11），最后前端（R7）。

### 阶段 1: DB 层（R10 单例连接 + R3 失败文件清理）

- [ ] 1.1 `db.py`: 改 `_get_db` 为单例连接，`init_db` 初始化全局连接并设置 PRAGMA，新增 `close_db()`。
- [ ] 1.2 `db.py`: 移除所有函数的 `finally: await db.close()`（全文替换，机械改动）。逐个函数确认连接在异常时不泄漏（单例由 `close_db` 统一管理）。
- [ ] 1.3 `db.py`: 新增 `cleanup_failed_task_files(max_age_days=7)` 函数。
- [ ] 1.4 `main.py`: lifespan 中 `recover_incomplete_tasks` 后调用 `cleanup_failed_task_files()`；finally 中调用 `close_db()`。
- [ ] 1.5 `backend` 下 `uv run ruff check .`、`uv run pytest` 通过。
- [ ] **验证门**: 启动服务，注册/登录正常，创建任务不报 DB 错误。

### 阶段 2: 服务层 — ASR（R4 切分健壮化 + R5 进度回调）

- [ ] 2.1 `transcribe.py`: `_transcribe_large_file` 增加 ffprobe returncode 检查、duration 判空、`chunk_duration` 下限 30s。
- [ ] 2.2 `transcribe.py`: `_transcribe_large_file` 和 `_transcribe_file` 增加 `progress_cb` 参数；`transcribe_audio` 透传 `progress_cb`。
- [ ] 2.3 `transcribe.py`: 大文件路径每个 chunk 完成后 `progress_cb(start/total, msg)`；小文件路径完成后 `progress_cb(1.0, msg)`。
- [ ] 2.4 `backend` 下 `uv run ruff check .` 通过。
- [ ] **验证门**: 单元测试若有则跑；手动验证大文件 ASR 不崩。

### 阶段 3: 服务层 — 笔记生成（R8 LLM 重试 + R9 分块生成）

- [ ] 3.1 `note_gen.py`: 新增 `_is_retryable(exc)` helper（识别 RateLimitError/Timeout/Connection/5xx）。
- [ ] 3.2 `note_gen.py`: `generate_notes` / `_generate_notes_single` 包装重试循环（最多 3 次，退避 2s/4s）。
- [ ] 3.3 `note_gen.py`: 新增 `_split_transcript(transcript, max_chars)` 按行分块。
- [ ] 3.4 `note_gen.py`: 重构 `generate_notes`：单块走原路径；多块分块生成 + `_merge_notes` 合并。
- [ ] 3.5 `note_gen.py`: 新增 `_merge_notes(sub_notes, ...)` —— 拼接后调 LLM 统一标题层级与总览。
- [ ] 3.6 `backend` 下 `uv run ruff check .` 通过。
- [ ] **验证门**: 短转录走单块路径不变；长转录分块生成完整笔记。

### 阶段 4: 服务层 — yt-dlp 错误分类（R7）

- [ ] 4.1 `subtitle.py`: 新增 `classify_ytdlp_error(exc) -> str`。
- [ ] 4.2 `subtitle.py`: 新增 `get_video_info_strict(url, ...)`，失败时抛带 `.code` 属性的异常。
- [ ] 4.3 `backend` 下 `uv run ruff check .` 通过。

### 阶段 5: 路由层（R1/R2/R5 胶水/R6/R7 消费/R11）

- [ ] 5.1 `routes.py`: 新增 `_subtitle_languages(note_lang)` helper（R1）。
- [ ] 5.2 `routes.py`: `_process_video_url` 调 `extract_subtitles` 传入 `languages=_subtitle_languages(language)`（R1）。
- [ ] 5.3 `routes.py`: `_process_video_url` 拆分 video info 与 thumbnail 的 try 块（R2）；video info 改用 `get_video_info_strict`（R7），失败时 `code = getattr(e, "code", "VIDEO_FETCH_FAILED")`。
- [ ] 5.4 `routes.py`: ASR 调用处增加 `_asr_progress_cb` 闭包，通过 `asyncio.run_coroutine_threadsafe` 调度 `update_progress`（R5）。
- [ ] 5.5 `routes.py`: `task_progress` SSE 加 30 分钟超时 + 15 秒 `ping` 心跳（R6）。
- [ ] 5.6 `routes.py`: 统一进度数值（R11）——字幕路径 `0.1→0.2`；确认 ASR 路径与字幕路径在 `generating` 阶段后对齐。
- [ ] 5.7 `backend` 下 `uv run ruff check .`、`uv run pytest` 通过。
- [ ] **验证门**: 手动提交 URL 任务走完整链路；SSE 进度更新；私有视频报 VIDEO_PRIVATE。

### 阶段 6: 前端（R7 新增错误码 i18n）

- [ ] 6.1 `frontend/src/api/client.ts`: `TASK_MESSAGE_ERROR_CODES` 增加 `VIDEO_PRIVATE`、`VIDEO_GEO_RESTRICTED`、`VIDEO_NOT_FOUND`、`VIDEO_COOKIE_INVALID`。
- [ ] 6.2 `frontend/src/i18n/locales/en.json`: errors 对象增加对应键。
- [ ] 6.3 `frontend/src/i18n/locales/zh-CN.json`: 同上中文翻译。
- [ ] 6.4 `frontend` 下 `npm run lint`、`npm run build` 通过。

### 阶段 7: 全链路验证

- [ ] 7.1 `backend` 下 `uv run ruff check .` 与 `uv run pytest` 全绿。
- [ ] 7.2 `frontend` 下 `npm run lint` 与 `npm run build` 全绿。
- [ ] 7.3 手动验证矩阵（如条件允许）：
  - 中文视频 + zh-CN 语言 → 优先中文字幕（AC1）
  - 缩略图失败场景（构造防盗链）→ 任务不失败（AC2）
  - 提交私有视频 → 报 VIDEO_PRIVATE（AC9）
  - 长视频 → 分块生成完整笔记（AC11）
  - SSE 连接正常关闭与重连（AC7）

## 验证命令

```bash
# 后端
cd backend
uv run ruff check .
uv run pytest

# 前端
cd frontend
npm run lint
npm run build
```

## 回滚点

- 阶段 1（R10 单例连接）风险最高。若单例连接导致死锁或性能问题，回滚 `_get_db` 为每次新建，恢复 `finally: close()`。
- 阶段 3（R9 分块生成）若 LLM 成本或失败率异常，可 fallback 为截断 + 警告提示（保留 `_split_transcript` 但 `_merge_notes` 失败时回退拼接）。