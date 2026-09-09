# Implementation Plan: Fix retry restarting from scratch

## 执行清单（按序）

### 1. D1 — failed 终态不清理文件
- [ ] `backend/app/pipeline/orchestrator.py`：`_finalize_failed` 移除 `_cleanup_files(job_id)` 调用（加注释说明 failed 保留文件供 retry 续跑，延迟清理由 `db.cleanup_failed_task_files` 兜底）。
- [ ] 确认 `_finalize_cancelled` / `_maybe_cancelled` / `_finalize_complete` 保持全量清理不变。

### 2. D2 — rewind 保留 resume 语义
- [ ] `orchestrator.py` `run()`：WAV 缺失分支改为 `phase = PipelinePhase.audio`，不再清空 `checkpoint` / `artifacts` / `was_resumed`；更新该分支注释（"re-run audio only; artifacts keep fetch/subtitle skippable"）。
- [ ] 检查 FILE_PATH（upload）resume 到 transcribe 且 WAV 缺失场景：回退到 audio 后 `input_path` 仍在 extra（failed 不再删输入文件），audio stage 可正常执行。

### 3. D3 — 删除任务时清理 WAV
- [ ] `backend/app/api/routes.py` `cancel_or_delete_task`：在删除分支增加 `wav_path_for(job_id).unlink(missing_ok=True)`（从 `app.pipeline.context` 导入）。

### 4. D4 — 延迟清理覆盖 WAV
- [ ] `backend/app/db.py` `cleanup_failed_task_files`：删除输入文件的同时 `wav_path_for(job_id).unlink(missing_ok=True)`。注意 db.py 不应依赖 pipeline 层（检查现有 import 方向；若会引入反向依赖，把 WAV 路径规则提为 db.py 内小函数或从 `app.config` 读取基目录，保持分层干净——实现时以现有分层约定为准，参考 `.trellis/spec/backend`）。

### 5. R4 — 测试
- [ ] test_orchestrator（或新增）：URL 任务 transcribe 失败 → retry，断言 fetching/subtitle/audio 未重跑（WAV 在场，直接 resume transcribe）。
- [ ] WAV 被外部删除 → retry，断言仅 audio+transcribe 重跑，fetching/subtitle 靠 artifact 跳过。
- [ ] upload 任务失败 → retry 成功。
- [ ] failed 终态文件保留；complete / cancelled / 删除任务 / 延迟清理路径各自正确删除 WAV 与输入文件。

### 6. 文档
- [ ] `docs/pipeline-contract.md`：如第 131/141 行描述需要补充 failed 保留文件的细节，最小化更新。

## 验证命令

```bash
cd backend && python -m pytest tests/pipeline/ -x -q
```

## 风险文件 / 回滚点

- `backend/app/pipeline/orchestrator.py`（核心行为改动，回滚点 = 单独 commit）
- `backend/app/db.py`（分层方向需注意）
- `backend/app/api/routes.py`

## start 前检查

- [ ] implement.jsonl / check.jsonl 已含真实条目（sub-agent 模式）
