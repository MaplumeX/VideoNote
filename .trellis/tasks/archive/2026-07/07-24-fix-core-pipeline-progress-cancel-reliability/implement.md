# Implement — 修复核心链路进度反馈与取消恢复可靠性

> 有序 checklist。每步标注验证方式。Review gate 在 G1、G2。

## Phase A — 后端进度语义与错误码（R1.1/R1.2, R8.2）

- [ ] A1 `backend/app/api/routes.py` `_process_video_url`：重排进度区间，无字幕回落路径不再回退（下载音频 0.15–0.25，转写 0.30–0.60，生成 0.65–0.95）。验证：日志追踪进度值单调。
- [ ] A2 `_process_video_file`：音频提取改为 `TaskStage.downloading, 0.05–0.15` + message "Extracting audio"；转写 0.20–0.60。验证：stage 序列不含 transcribing 表达音频提取。
- [ ] A3 `_process_video_file` 音频提取失败 message 改 `AUDIO_EXTRACTION_FAILED`（替代 `VIDEO_FETCH_FAILED`）。
- [ ] A4 前端 `errors` 翻译新增 `audioExtractionFailed` 键（en/zh-CN）。

## Phase B — 前端进度展示与失败定位（R2.1, R3.1, R1.2 指示器）

- [ ] B1 `frontend/src/components/StepIndicator.tsx`：新增 `sourceType?: "url" | "upload"` prop；步骤集按 sourceType 切换；`download` step label 对 upload 改为「提取音频」。
- [ ] B2 `StepIndicator.getStepStatuses`：failed/cancelled 时按 progress 阈值(<0.3/0.65)定位失败步骤，仅该步及之后标 error，之前保持 done。
- [ ] B3 `frontend/src/pages/NewNotePage.tsx`：处理中在 StepIndicator 下方实时显示 `progress?.message`（无则空）。失败/取消时不显示（StepIndicator 已表达）。
- [ ] B4 NewNotePage 向 StepIndicator 传 `sourceType`（由 taskMeta.source_type 推导）。
- [ ] 验证 G1：`cd frontend && npm run test && npm run build`（前端单测 + 构建）。

## Phase C — 取消深入阻塞调用（R4.1, R4.2）

- [ ] C1 `backend/app/task_runner.py`：`schedule` 创建 `threading.Event` 存 `self._cancel_events[job_id]`；`cancel`/`cancel_and_wait` 置位；`_discard` 清理；`shutdown` 一并置位。`TaskFactory` 签名升级为 `Callable[[threading.Event], Awaitable[None]]`（或 factory 返回的协程闭包内捕获 event）。
- [ ] C2 `routes.py` `_process_video_url`/`_process_video_file`：在 `_run` 闭包内创建/获取 event，传入各 service 调用；`_asr_progress_cb` 内检查 event 提前返回 None。
- [ ] C3 `subtitle.py`：`extract_subtitles`/`download_audio_via_ytdlp`/`get_video_info_strict` 新增 `cancel_event` 参数；yt-dlp 调用挂 `progress_hooks`，hook 内 `if cancel_event.is_set(): raise yt_dlp.utils.DownloadCancelled(...)`。
- [ ] C4 `audio.py`：`extract_audio` 用 `subprocess.Popen` + 手动 wait，取消时 `proc.terminate()`/`kill()`。
- [ ] C5 `transcribe.py`：`transcribe_audio`/`_transcribe_large_file` 新增 `cancel_event`，每个 chunk 处理前检查并 `raise asyncio.CancelledError` 不适用（线程内）→改为返回空串或抛 `RuntimeError("cancelled")`，由外层捕获翻译为 cancelled。chunk 间检查点。
- [ ] C6 `note_gen.py`：`generate_notes`/`_call_llm`/`_merge_notes` 间增加 `cancel_event` 检查点；chunk 之间检查。
- [ ] 验证 G2：`cd backend && python -m pytest tests/ -q`；并手动脚本（或单测）模拟取消一个长 ASR/LLM 任务，断言底层尽快返回且 stage=cancelled。

## Phase D — 恢复上限（R5.1）

- [ ] D1 `db.py`：新增常量 `MAX_TASK_ATTEMPTS=5`；`increment_attempt` SQL 加 `AND attempt_count < ?` 并返回受影响行数；超限返回 False。
- [ ] D2 `recover_incomplete_tasks`：`task_runner.schedule` 后检查——若 `increment_attempt` 返回 False（schedule 内已调用），需要在恢复流程中将其标记 failed（message `TASK_RECOVERY_MAX_ATTEMPTS`）。实现上：`recover_incomplete_tasks` 在调度前预检查 attempt_count，超限直接 `update_progress(failed, ..., "TASK_RECOVERY_MAX_ATTEMPTS")`。
- [ ] D3 前端 `TASK_MESSAGE_ERROR_CODES` 加入 `TASK_RECOVERY_MAX_ATTEMPTS` + 翻译键。
- [ ] 验证：单测构造 attempt_count=5 的任务，重启恢复后被标记 failed 且不再调度。

## Phase E — 长视频笔记进度与截断续写（R6.1, R6.2）

- [ ] E1 `note_gen.py`：`generate_notes` 接受 `progress_cb: Callable[[float, str], None] | None`；多 chunk 时每 chunk 完成上报（0.70→0.90 插值，message "Generating notes {i}/{n}"）；合并前 0.92 message "Merging notes"；完成 0.95。
- [ ] E2 `routes.py`：两个 `_process_*` 调用 `generate_notes` 处传 progress_cb（同 ASR `run_coroutine_threadsafe(update_progress(...))` 模式）。注意 `generating_notes` 阶段已先有 0.65/0.7 等，统一用 callback 产出。
- [ ] E3 `note_gen._call_llm`：返回前检查 `finish_reason=="length"`，若是用续写请求（携带已生成文本作为 prefix，prompt 要求继续），最多续写 2 次；拼接。
- [ ] 验证：单测 mock OpenAI 返回 finish_reason=length，断言续写被触发且最终 markdown 完整。

## Phase F — 重复提交去重（R7.1）

- [ ] F1 `db.py`：新增 `find_active_task_by_url(user_id: str, url: str) -> dict | None`（stage 非终态、`cancel_requested=0`、video_url 匹配、按 created_at desc 取首条）。
- [ ] F2 `routes.py` `process_video`：提交前查询，命中则直接返回既有 job_id（`ProcessResponse` 复用，可附 `is_duplicate=True`）。前端无需改 UI。
- [ ] 验证：单测同 URL 二次提交返回相同 job_id，无新任务记录。

## Phase G — 错误信息不泄漏（R8.1）

- [ ] G1 `routes.py` `/models`：`except Exception` 分支返回 `error="MODELS_FETCH_FAILED"`，不返回 `str(e)`；保留 `logger.warning` 完整异常。
- [ ] G2 前端 `SettingsPage` 若直接展示 `error` 文本，改为翻译 `errors.modelsFetchFailed`；并在 `translateApiError` / `TASK_MESSAGE_ERROR_CODES` 加入 `MODELS_FETCH_FAILED`。
- [ ] 验证：调用 `/models` with bad key，响应 error 不含 'openai' / url / traceback。

## Phase H — 回归与收尾

- [ ] H1 `cd backend && python -m pytest tests/ -q` 全绿。
- [ ] H2 `cd frontend && npm run test && npm run build` 全绿。
- [ ] H3 `python3 ./.trellis/scripts/task.py start` 前 review：prd/design/implement 一致。
- [ ] H4 更新 `.trellis/spec/backend` 与 frontend 规范中受影响段落（若有新约定）。
- [ ] H5 commit。

## Review Gates

- G1（Phase B 后）：前端进度展示与失败定位可用、单测绿。
- G2（Phase C 后）：取消深入阻塞调用验证通过。
- 最终 gate：所有 Phase 单测与手动验证通过，进入 Phase 3 收尾。

## 回滚点

- Phase 间相互独立：A/B（前端体验）、C（取消）、D（恢复）、E（长视频）、F（去重）、G（泄漏）可独立 revert。
- task_runner 签名升级（C1）影响面最大，单列 commit 便于回滚。