# 子任务 C1：任务状态机与持久层（契约基线）

## Goal

为核心流水线重写建立契约基线：阶段状态机数据模型、统一错误码体系、两级进度模型、DB 检查点/中间产物持久化迁移，以及固化新 SSE/API 契约的契约文档。本任务是后续所有子任务（C2~C5）的依赖。

## Dependencies

- 无前置子任务。
- 完成后契约冻结：state/errors/progress 的任何变更需回父任务评审。

## Scope（父任务 design.md §1/§2 的契约部分）

- `pipeline/state.py`：新阶段枚举（URL 路径 `pending→fetching→subtitle→transcribe→notegen→complete`，文件路径 `pending→audio→transcribe→notegen→complete`）、检查点数据模型。
- `pipeline/errors.py`：统一错误码枚举（含现有 VIDEO_* / TRANSCRIPTION_FAILED / NOTE_GENERATION_FAILED / PROVIDER_NOT_CONFIGURED 等语义归集）、`PipelineError`、集中脱敏。
- `pipeline/progress.py`：两级进度模型（stage + phase_progress）与事件发布接口。
- DB 迁移：tasks 表新增 `checkpoint_stage` / `attempt_count` / `last_error_code`；新表 `task_artifacts`（kind: subtitle|transcript|video_meta）；沿用 schema_version 机制。
- 契约文档：阶段枚举、SSE 事件 schema、REST 变更点，供 C2~C5 与前端引用。

## Acceptance Criteria

- [ ] 状态机覆盖两条路径全部阶段与 failed/cancelled 终态转移，非法转移被拒绝（单元测试）。
- [ ] 错误码枚举集中定义，脱敏函数一处实现且有测试（API key/cookie 泄漏用例）。
- [ ] DB 迁移幂等可重入，旧数据行 checkpoint 为空时行为定义为"从头执行"（迁移测试）。
- [ ] 契约文档评审通过（父任务 G1 门禁）。

## Notes

- 详细 design.md / implement.md / implement.jsonl / check.jsonl 在本任务启动前完成（父规划已批准即轮到本任务细化）。
