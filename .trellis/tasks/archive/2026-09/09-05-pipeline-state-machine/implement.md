# 执行计划：C1 任务状态机与持久层（契约基线）

## Checklist（有序）

### Part A：契约模块（纯新增）
- [ ] A1 创建 `backend/app/pipeline/__init__.py` 与 `pipeline/stages/__init__.py`
- [ ] A2 `pipeline/state.py`：`TaskStatus` / `PipelinePhase` / `URL_PATH` / `FILE_PATH` / `ALLOWED_TRANSITIONS` / `validate_transition` / `next_phases` / `resume_point` / `Checkpoint` / `ArtifactKind`
- [ ] A3 `pipeline/errors.py`：`ErrorCode` / `PipelineError`（构造即脱敏）/ `sanitize_detail` / `InvalidTransitionError`
- [ ] A4 `pipeline/progress.py`：`ProgressEvent` / `ProgressPublisher` 协议 / `PhaseProgressTracker`（clamp + 单调守卫）
- [ ] A5 `pipeline/stages/base.py`：`StageContext` / `StageResult` / `Stage` 协议 / `ArtifactStore` 协议 / `ProviderConfig` dataclass

### Part B：DB 迁移与持久化
- [ ] B1 `app/db.py`：tasks 新增列（status/phase/phase_progress/checkpoint_phase/last_error_code）+ 存量回填 UPDATE
- [ ] B2 `app/db.py`：`task_artifacts` 表 + `save_artifact` / `get_artifact`
- [ ] B3 `app/db.py`：`save_checkpoint` / `read_checkpoint`（条件写：非终态 + cancel_requested=0）

### Part C：契约文档
- [ ] C1-1 `docs/pipeline-contract.md`（阶段转移图、SSE 载荷 schema、kinds 表、错误码全表、Stage 接口）

### Part D：测试
- [ ] D1 `tests/pipeline/test_state.py`
- [ ] D2 `tests/pipeline/test_errors.py`
- [ ] D3 `tests/pipeline/test_progress.py`
- [ ] D4 `tests/pipeline/test_db_migration.py`

## 验证命令

```bash
cd backend
uv run ruff check app/ tests/
uv run python -m pytest tests/ -q          # 全量（含旧 74 个测试，验证未破坏旧链路）
```

## 边界与禁止事项

- **禁止修改**：`app/services/**`、`app/api/routes.py` 的现有行为、`app/task_runner.py`。旧链路必须保持测试全绿。
- 旧 `TaskStage`（schemas.py）不删除不改动——新枚举并存，C4 切换。
- DB 迁移必须幂等（重复 init_db 不报错、不重复回填）。

## 风险与回滚

- 回填 UPDATE 若映射有误会影响旧任务展示 → 用内存 SQLite 双版本迁移测试覆盖；回填 WHERE 限定 `status IS NULL`（只跑一次）。
- 本任务全部为增量，revert 单 commit 即回到原状。

## 完成定义

- 全部 checklist 完成，ruff + pytest 全绿（含旧测试）
- G1 门禁材料就绪：契约文档 + 测试报告，提交父任务评审
