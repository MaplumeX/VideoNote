# Design — 修复核心链路进度反馈与取消恢复可靠性

## 影响面

- 后端：`backend/app/api/routes.py`、`backend/app/task_runner.py`、`backend/app/services/{note_gen,transcribe,subtitle,audio}.py`、`backend/app/db.py`
- 前端：`frontend/src/pages/NewNotePage.tsx`、`frontend/src/components/StepIndicator.tsx`、`frontend/src/hooks/useSSE.ts`（可能）、`frontend/src/types/index.ts`（可能）
- 测试：`backend/tests/`、`frontend/src/**/*.test.ts`

## 设计决策

### D1 进度模型：阶段内单调 + 显式区间映射

不引入新 stage 枚举，沿用现有 `TaskStage`，但用统一区间表约束每段进度，并在「无字幕回落」路径上不再回写更小值。

区间表（URL 流程，有字幕）：
- extracting_subtitles: 0.10–0.30（找到字幕→0.30）

区间表（URL 流程，无字幕回落）：
- extracting_subtitles: 0.10（查找中）
- downloading: 0.15–0.25（下载音频）
- transcribing: 0.30–0.60（ASR 进度映射到此区间）
- generating_notes: 0.65–0.95

上传文件流程：
- 新增语义：提取音频用 `downloading` stage（0.05–0.15），表示「准备音频」；不再用 `transcribing` 表达音频提取。
- transcribing: 0.20–0.60
- generating_notes: 0.65–0.95

这保证进度单调不减。DB 的 `update_progress` 终态守护不变。

### D2 前端 step 指示器按 source_type 选择步骤集

`StepIndicator` 接收 `sourceType?: "url" | "upload"`：
- url: [下载, 转写, 生成]
- upload: [提取音频, 转写, 生成]

上传流程第一段（提取音频）落到 step 1，stage `downloading` 命中 step 1 active。`transcribing` 落 step 2，`generating_notes` 落 step 3。

### D3 失败步骤定位

`StepIndicator.getStepStatuses` 由「全红」改为「当前及之后标红、之前保持 done」：
- failed 在 downloading/extraction → ["error","pending","pending"]
- failed in transcribing → ["done","error","pending"]
- failed in generating → ["done","done","error"]
- cancelled 同理。

`StepIndicator` 新增可选 `failedStage?: TaskStage | null`（或从 stage===failed && 当前进度推断），最简：传 `stage` 与 `progress` 即可推断——失败时用 progress 落点推断失败阶段。更稳妥：`useSSE` 已保存最后非终态 stage 到 `stageRef`，但传到 NewNotePage 较绕。采用「失败时按 progress 阈值推断」：progress<0.3 → 步骤1；<0.65 → 步骤2；否则步骤3。简单、足够准。

### D4 取消深入阻塞调用

核心：`to_thread` 的函数支持接收一个 `cancel_event: threading.Event`（或等价的 `is_cancelled` 回调），在关键同步调用点检查并尽快返回。

- `subtitle.get_video_info_strict` / `extract_subtitles` / `download_audio_via_ytdlp`：yt-dlp 不原生支持中途取消，但可以把 `ydl.download` / `extract_info` 放进线程，外层用 `cancel_event` 在 yt-dlp 的 `progress_hooks` 中抛 `yt_dlp.utils.DownloadCancelled`（yt-dlp 支持 progress_hooks 抛异常中止下载）。这是最小侵入的真·取消。
- `audio.extract_audio` / ffmpeg 子进程：`subprocess.Popen` 保留句柄，取消时 `proc.terminate()`/`kill()`。
- `transcribe.transcribe_audio`（OpenAI 同步 client）：OpenAI 不支持取消 in-flight 请求；在每 chunk 之间检查 cancel_event，单 chunk 不可取消但尽快返回。长文件的 chunk 间检查点已存在（循环内），补 `cancel_event` 检查。
- `note_gen.generate_notes`：多 chunk 生成与合并之间检查 `cancel_event`；单次 LLM 调用不可中断，但 `_call_llm` 重试间与 chunk 间可检查。

实现：工厂闭包内在 `_run` 创建 `threading.Event`，传给工厂产出的协程；`task_runner.cancel(job_id)` 除 `task.cancel()` 外置位该 Event。`TaskRunner` 维护 `dict[str, threading.Event]`，`schedule` 创建，`cancel` 置位，`_discard` 清理。

ASR 进度回调 `_asr_progress_cb` 内也可检查 event 提前返回。

### D5 恢复上限

`db.py`：
- `increment_attempt` 改签名为 `try_claim_attempt(job_id, *, max_attempts=5) -> bool`，SQL 加 `AND attempt_count < ?`。返回 False 表示超限。
- `get_recoverable_tasks` 查询条件追加 `AND attempt_count < 5`。
- 超限的任务由恢复流程标记 failed（message `TASK_RECOVERY_MAX_ATTEMPTS`，加入 `TASK_MESSAGE_ERROR_CODES` 翻译）。

常量 `MAX_TASK_ATTEMPTS = 5`。

### D6 长视频笔记进度与截断续写

`note_gen.py`：
- `generate_notes` 多 chunk 时接受 `progress_cb`，每个 chunk 完成上报 `generating_notes` 进度 0.70 → 0.90 线性插值；合并阶段上报 0.92，完成 0.95。
- `routes.py` 调用处传入与 `update_progress` 对接的 callback（同 ASR 的 `run_coroutine_threadsafe` 模式）。
- 截断检测：`_call_llm` 后检查 `response.choices[0].finish_reason == "length"`，若是则发起续写请求（带上已生成内容，让模型从断点继续），拼接结果。续写最多 2 次，超出则记录 warning 并用已有内容。

### D7 重复提交去重

`db.py` 新增 `find_active_task_by_url(user_id, url) -> dict | None`：查询同 user、同 video_url、stage 非终态的任务。
`routes.py` `process_video`：提交前查询，存在则返回既有 job_id（响应 附 `is_duplicate: true` 标记或直接复用）。采用「返回既有 job_id」，前端 `NewNotePage` 已据此直接进入进度跟踪，无需改 UI。

去重键仅 `video_url`（+ user）。上传文件不参与去重（每次都不同文件）。

### D8 错误信息不泄漏

- `/models`：`except Exception` 分支不返回 `str(e)`，改为返回 `ModelsResponse(models=[], error="MODELS_FETCH_FAILED")`，前端按 code 翻译。前端 `SettingsPage` 调用处适配（若它直接显示 error 文本，改为翻译）。
- 上传提取音频失败：`_process_video_file` 音频提取失败 message 改为 `AUDIO_EXTRACTION_FAILED`，加入翻译表。
- 错误码常量集中：新增的 `AUDIO_EXTRACTION_FAILED`、`TASK_RECOVERY_MAX_ATTEMPTS`、`DUPLICATE_TASK`（若用）、`MODELS_FETCH_FAILED` 加入 `TASK_MESSAGE_ERROR_CODES` 或前端 `errors.*` 翻译键。

## 数据流与契约

- 进度更新契约不变：`{stage, progress, message}`，前端无需改 schema。
- `ProcessResponse` 可选新增 `is_duplicate?: boolean`（向后兼容），可选不暴露给前端即可。
- DB schema 无变更（attempt_count 列已存在）。

## 兼容性 / 回滚

- 所有改动向后兼容：无 schema 迁移；前端 `StepIndicator` 新增 `sourceType` 可选 prop，缺省时行为退化为现状（保持 url 三步）。
- 回滚：各修复点相互独立，可分文件 revert；无破坏性依赖。

## 风险

- yt-dlp progress_hooks 抛 `DownloadCancelled` 取决于 yt-dlp 版本行为；若不稳定则退化为「请求级尽快返回 + chunk 间检查」，已 acceptable。
- LLM 续写拼接可能产生轻微重叠；通过 `normalize_note_markdown` 规整，风险可接受。