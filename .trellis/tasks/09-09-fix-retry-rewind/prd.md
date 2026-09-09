# Fix retry restarting from scratch: preserve WAV and reuse artifacts on rewind

## Goal

让 `POST /tasks/{id}/retry` 真正兑现"从 checkpoint 续跑"的契约（docs/pipeline-contract.md:141）：失败任务重试时不再从头开始整个 pipeline，且 upload 任务在失败后仍可成功重试。

## Background / Confirmed Facts（代码证据）

1. **failed/cancelled 终态即刻删除恢复所需文件**：`Orchestrator._cleanup_files`（backend/app/pipeline/orchestrator.py:307-319）在所有终态（含 failed、cancelled）删除 per-job WAV 和 upload 输入文件，并 `clear_task_input_file()` 清空 DB 路径。
2. **WAV 丢失导致全量 rewind**：`Orchestrator.run`（orchestrator.py:96-110）在 resume 到 transcribe 且 WAV 缺失时，将 checkpoint 整体丢弃、回退到 `plan.path[0]`（URL 任务 = fetching），且 `was_resumed=False`、`artifacts=frozenset()`，导致 fetch/subtitle/transcribe 的 artifact 跳过逻辑全部失效——注释声称"re-run the audio phase"，实际回到整个路径起点。
3. **audio 是最耗时且最易因网络失败的 phase**（yt-dlp 下载），却没有任何持久化产物（音频刻意不进 DB）；其产物仅为 `tmp/videonote_pipeline_audio/{job_id}.wav`（context.py `wav_path_for`）。
4. **upload 任务失败后重试必然再失败**：`_cleanup_files` 删除上传文件并清空 `input_file_path` 后，重试时 audio stage 拿不到 `input_path`/`url`，抛 `"neither url nor input_path in stage context"`。
5. **已有延迟清理机制**：`db.cleanup_failed_task_files`（db.py:271，7 天）删除 failed 任务的输入文件；`db.cleanup_old_terminal_tasks`（db.py:304，30 天）删除终态任务及输入文件。即"失败任务的文件早晚要清"已有专门通道，终态即刻删除是多余且有害的。
6. **cancelled 任务同样可重试**：routes.py `retry_task` 的 `retryable = {failed, cancelled}`，故 cancelled 终态删文件同样破坏可重试性。
7. **stage 层 resume 跳过逻辑已完备**：fetch/subtitle/transcribe 在 `resume=True` 且 artifact 存在时直接跳过（各 stage `run()` 开头）。
8. **notegen 无持久化中间态**：分片笔记仅存内存，重试整段重跑（幂等、安全，预期行为）。

## Requirements

### R1：failed 终态不删除恢复所需文件；cancelled 维持现状
- `_finalize_failed` / 失败路径的 `_maybe_cancelled` 不再删除 per-job WAV 和 upload 输入文件，不再 `clear_task_input_file()`。
- cancelled 终态维持现状（即刻清理 WAV 与输入文件）——用户主动取消视为放弃，取消后 retry 走"WAV 缺失 rewind"路径（R2），artifact 跳过逻辑仍生效。
- complete 终态维持现状（全量清理）。

### R2：WAV 缺失时的 rewind 保留 resume 语义
- resume 到 transcribe 但 WAV 缺失时，仅回退到 audio phase（不是 `path[0]`），并保留 checkpoint 推导的 artifacts 与 `was_resumed=True`，使 fetching/subtitle 经 artifact 检查跳过。
- 对 FILE_PATH（upload）任务同理回退到 audio。

### R3：遗留文件有明确的最终清理路径
- 删除任务（DELETE /tasks/{id}）时同时清理 WAV（当前只删 upload 输入）。
- 延迟清理覆盖 failed 任务的 retained 文件：`cleanup_failed_task_files` 同时删除输入文件与 per-job WAV。

### R4：测试覆盖
- failed（transcribe 阶段失败）→ retry：不重跑 fetching/subtitle/audio（WAV 保留时直接 resume transcribe）。
- WAV 被外部清理 → retry：仅重跑 audio + transcribe，fetching/subtitle 跳过。
- upload 任务 failed → retry：可成功（输入文件保留）。
- complete / 删除任务 / 延迟清理仍正确清理 WAV 与输入文件。

## Acceptance Criteria

- [ ] URL 任务在 transcribe 失败后 retry，日志/测试断言 fetching、subtitle、audio 均未重新执行（WAV 在场）。
- [ ] 人为删除 WAV 后 retry，仅 audio 与 transcribe 重跑，fetching/subtitle 不重跑。
- [ ] upload 任务失败后 retry 成功完成。
- [ ] 任务 complete、被删除、被取消、或 failed 延迟清理到期时，WAV 与 upload 输入文件均被删除。
- [ ] 现有测试套件（backend/tests/pipeline/）全部通过。

## Key Decisions

- **方案 B（用户已确认）**：failed 任务保留 WAV 与上传文件以支持断点续跑；cancelled 任务不保留（用户主动取消视为放弃）。代价：cancelled 任务的 retry 若 WAV 缺失则回退到 audio 重跑（fetching/subtitle 仍靠 artifact 跳过）；upload 任务 cancelled 后 retry 仍会因输入文件缺失而失败（现状行为，接受）。

## Out of Scope

- notegen 分片中间态持久化（`notes_draft` ArtifactKind 已预留但本任务不实现）。
- 前端改动（retry API 契约不变）。
- 重试次数上限 / 退避策略调整。
