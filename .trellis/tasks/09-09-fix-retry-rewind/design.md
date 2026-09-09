# Design: Fix retry restarting from scratch

## 问题本质

checkpoint 续跑依赖两类输入：持久化 artifact（DB，已可靠）和 per-job 临时文件（WAV、upload 输入，仅文件系统）。当前失败终态把第二类删掉，而 rewind 逻辑又把第一类的价值也一并丢弃，导致重试 = 全量重跑。

## 改动点

### D1：终态清理按终态分流（orchestrator.py）

`_cleanup_files` 拆成两种行为：

- `_cleanup_files(job_id)`：保持现状（删 WAV + upload 输入 + `clear_task_input_file`），调用方：`_finalize_complete`、`_finalize_cancelled`、`_maybe_cancelled`（cancelled 收敛路径）。
- failed 路径（`_finalize_failed`）：**不清理任何文件**。WAV 与 upload 输入保留，供 retry 续跑。

`_maybe_cancelled` 的语义是"取消赢了竞态 → 收敛到 cancelled"，因此保留全量清理。

### D2：WAV 缺失 rewind 保留 resume 语义（orchestrator.py `run()`）

现状（orchestrator.py:96-110）：WAV 缺失 → `checkpoint = None; phase = plan.path[0]; was_resumed = False; artifacts = frozenset()`。

改为：WAV 缺失 → 仅回退 phase 到 `PipelinePhase.audio`（URL 与 FILE 路径的 audio 均为合法 resume 点；FILE_PATH[0] 本身就是 audio），**保留** checkpoint 推导的 artifacts 与 `was_resumed=True`：

- `phase = PipelinePhase.audio`
- `artifacts`、`was_resumed` 不变

效果链：fetching/subtitle 不在后续 path 中直接被跳过（audio → transcribe → notegen）；即使将来路径扩展，stage 的 resume 短路（`resume=True` + artifact 存在）也保证不重跑。

边界情况：checkpoint 恰为 `audio` 完成但 WAV 缺失（理论上 `resume_point` 会给 transcribe，走到这条 rewind 分支的只有 transcribe/notegen resume 场景）。对 notegen resume（subtitle-hit 路径，`transcribe` 未跑），`resume_point` 返回 notegen，不进入 WAV 检查分支——现有代码只对 `transcribe` 检查 `_restore_audio_path`，notegen 不需要 audio_path，行为不变，无需处理。

### D3：删除任务时清理 WAV（api/routes.py `cancel_or_delete_task`）

现状只删 upload 输入。增加 `wav_path_for(job_id).unlink(missing_ok=True)`。删除是终局操作，任何 retained 文件都应随之消失。

### D4：延迟清理扩展（db.py `cleanup_failed_task_files`）

现状只删 failed 任务（>7 天）的 upload 输入。扩展为同时删 per-job WAV。WAV 路径规则（`tmp/videonote_pipeline_audio/{job_id}.wav`）从 job_id 即可推导，无需 DB 存路径。

cancelled 任务不在此列（D1 已即刻清理）；complete 同理。

## 数据流 / 契约影响

- API 契约不变：`POST /tasks/{id}/retry` 仍是 checkpoint-resumed 语义，只是兑现程度提高。
- `docs/pipeline-contract.md:141` 的描述（"completed phases with durable artifacts are not re-executed"）从"部分兑现"变为"兑现"。
- 磁盘占用：failed 任务最多滞留一个 WAV（几十 MB 量级）+ upload 输入，7 天上限。

## 权衡与风险

- **cancelled 后 retry 的 upload 任务仍会失败**（输入文件已删）：方案 B 已接受，属现状行为。
- **保留文件绕过 `_cleanup_files` 的单点语义**：D1 拆分后清理职责分散到 delete / delayed-cleanup / complete / cancelled 四处，测试需覆盖每条路径（R4）。
- **WAV 滞留**：进程重启不清 tmp（现状即如此，tmp 目录由 OS 或部署层清理），7 天延迟清理兜底。

## 回滚

改动集中在 orchestrator 终态清理 + rewind 分支 + routes 删除 + db 延迟清理，均为行为级改动、无 schema 变更。回滚 = revert 提交即可。
