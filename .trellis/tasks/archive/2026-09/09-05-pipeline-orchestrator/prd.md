# 子任务 C4：流水线编排器与 API 层

## Goal

用状态机驱动的编排器替换 `routes.py` 内联的 `_process_video_url` / `_process_video_file` 巨型协程：从检查点恢复、统一取消语义、阶段驱动进度；REST/SSE 端点对接新契约；删除旧链路。

## Dependencies

- 依赖 C1（状态机/持久层/契约）、C2（转录阶段模块）、C3（笔记生成阶段模块）。
- 完成后 C5（前端适配）才能实施。

## Scope

- `pipeline/orchestrator.py`：
  - 按状态机顺序执行 stages；每阶段成功写检查点 + 中间产物；失败/取消进入终态。
  - 恢复逻辑：retry / 重启恢复时读取最后检查点，跳过已有产物阶段；attempt 上限（超出标 failed）。
  - 取消句柄管理：当前阶段的子进程/异步任务，API cancel → ≤3s 终止。
  - `task_runner.py` 重构：保留防重复调度，取消职责移交编排器（去 threading.Event）。
- `routes.py` 瘦身：只保留鉴权/校验/HTTP 映射；`_to_thread_with_cancel` / `_StageFailed` / `_make_*_progress_cb` 等删除；任务相关端点（process/upload/progress(SSE)/result/retry/cancel/恢复启动）对接新契约。
- 进程启动时未完成任务恢复（main.py）。
- 删除被替换的旧 `services/` 模块与对应旧测试，迁移仍复用的部分（markdown 归一化等）。

## Acceptance Criteria

- [ ] 集成测试（不依赖外网）：三条路径（有字幕 URL / 无字幕 URL→ASR / 文件上传）端到端出笔记（stages 用假实现或 fixture）。
- [ ] 取消集成测试：各阶段取消后 ≤3s 进入 cancelled，无残留子进程/任务。
- [ ] 恢复集成测试：LLM 阶段失败 → retry 不重跑转录（断言无第二次 ASR 调用）；attempt 上限生效；重启恢复正确。
- [ ] SSE 载荷符合 C1 契约文档；全程阶段单调、phase_progress ∈ [0,1]。
- [ ] `routes.py` ≤ ~400 行且无业务编排逻辑；旧链路代码（`_process_video_url` 等）及旧测试删除。
- [ ] 后端全量测试套件绿。

## Notes

- 本任务是新旧链路切换点，是回滚边界的最后可逆位置（C5 之前）。
