# 执行计划：C4 流水线编排器与 API 层

## Checklist（有序；Part D 是切换点，之前的每个 Part 完成后全量测试必须绿）

### Part A：runner 与上下文
- [ ] A1 `pipeline/runner.py`：PipelineTaskRunner（防重复调度、asyncio cancel、shutdown、无 threading.Event）
- [ ] A2 `pipeline/context.py`：`build_stage_context`（DB ArtifactStore 适配、进度发布→`update_progress` 新列、取消句柄注册表）+ `ExecutionPlan` + STAGES 注册表 + `advance`/`parse_checkpoint`

### Part B：orchestrator
- [ ] B1 `pipeline/orchestrator.py`：主循环（resume_point 起步、逐阶段执行、产物落库、检查点推进、extra 合并、终态条件写幂等）
- [ ] B2 终态与清理：failed(PipelineError)/cancelled(CancelledError)/complete(notes→result_json, video_meta→title/thumbnail)；上传文件/WAV/cookie 临时文件清理
- [ ] B3 `recover()`：可恢复任务矩阵（attempt 上限/无效输入/不支持 URL/URL/上传）+ 增量 attempt
- [ ] B4 retry 语义：仅 failed/cancelled 可重试、cancel_requested 重置、从检查点恢复

### Part C：API 层切换
- [ ] C1-1 `routes.py` 重写：删除旧编排/辅助函数；端点委托 orchestrator/runner；SSE 载荷换 ProgressEvent；响应模型换 status+phase 新枚举（旧 stage 列 COALESCE 展示）
- [ ] C2-1 `schemas.py`：TaskProgress/TaskListItem 等模型更新为新契约（旧 TaskStage 删除）
- [ ] C3-1 `main.py`：lifespan 改调 orchestrator.recover；task_runner 引用移除
- [ ] C4-1 `services/markdown.py` → `pipeline/markdown.py` 迁移（notegen import 更新）

### Part D：删除旧链路（切换点）
- [ ] D1 删除 `app/task_runner.py`、`app/services/{subtitle,audio,transcribe,note_gen}.py`
- [ ] D2 旧测试清理：针对已删模块的测试删除；仍有效的迁移（上传安全/SSE 解析/恢复矩阵）到 tests/pipeline/
- [ ] D3 docs/pipeline-contract.md 增补：REST 端点响应模型变更表（供 C5 使用）
- [ ] D4 `.trellis/spec/backend/` 中旧链路相关段落标记为已废弃（directory-structure 的 services 布局、error-handling 的旧编排示例、quality-guidelines 的 to_thread 规则）——标注替代物

## 验证命令

```bash
cd backend
uv run ruff check app/ tests/
uv run python -m pytest tests/ -q
```

## 边界与禁止事项

- **C1 冻结契约不改**：`pipeline/state.py`/`errors.py`/`progress.py`/`stages/` 五个阶段模块与 base.py 不改（发现阶段缺陷→报告主会话决策，不得顺手改）。
- 取消链路不得引入 threading.Event；SSE 载荷字段名以 docs/pipeline-contract.md 为准零漂移。
- `/upload` 的安全校验（类型白名单/大小/文件名净化）与 `/thumbnails` 路径遏制必须原样保留（P0 教训）。

## 风险与回滚

- 本任务是最大子任务，Part D 前旧链路仍在（可随时中止回滚到 C3 状态）；D 之后回滚需 revert 整个 C4 commit。
- 前端在 C4 合入后到 C5 完成前不可用——按父任务计划紧邻实施 C5。
- 旧测试删除误删有效覆盖 → 删除前列出清单逐个判断（保留/迁移/删除三选一）。

## 完成定义

- checklist 全完成；ruff + 全量 pytest 绿
- 集成测试覆盖：三条路径端到端（假 stage）、各阶段取消 ≤3s、retry 不重跑转录、重启恢复矩阵、SSE schema 断言
- `routes.py` ≤ ~450 行且无业务编排；G3 门禁材料就绪
