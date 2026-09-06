# 执行计划：C3 LLM 笔记生成重写

## Checklist（有序）

- [ ] 1 `pipeline/stages/notegen.py`：`LLMClient`（Async[OI] + 异步重试 + 续写）+ `NoteGenStage`（分块/合并/进度/错误包装）+ prompt 全量迁移（逐字符保真）
- [ ] 2 `stages/base.py`：确认 `StageResult.extra` 可用（C2 先行实现则直接用；若 C2 未完成则本任务添加——两任务并行时的合并顺序以先到者为准，字段定义一致：`extra: dict[str, object] = field(default_factory=dict)`）
- [ ] 3 `tests/pipeline/test_stage_notegen.py`：FakeLLMClient 全场景（单块/多块/续写/重试/取消/错误包装/prompt 快照）
- [ ] 4 同步 docs/pipeline-contract.md：notegen 阶段进度语义与 `extra` 用法说明

## 验证命令

```bash
cd backend
uv run ruff check app/ tests/
uv run python -m pytest tests/ -q
```

## 边界与禁止事项

- **禁止修改**：`app/services/**`（含 note_gen.py/markdown.py）、`app/api/routes.py`、`pipeline/state.py`/`errors.py`/`progress.py`。
- 禁止 `time.sleep`（异步 `asyncio.sleep`）、禁止同步 [OI] 客户端、禁止 to_thread。
- prompt 文本**逐字符迁移**，不允许改写/润色（行为对齐验收项）。
- 与 C2 并行开发：两者只可能同时触碰 `stages/base.py`（extra 字段）与 contract 文档——extra 字段定义已在本计划与 C2 计划中写成完全相同的文本，冲突时二选一即可。

## 风险与回滚

- prompt 快照测试依赖从旧文件拷贝期望值 → 实施时从 git HEAD 的 note_gen.py 直接提取，防止转录错误。
- 全部为新增文件，revert 单 commit 即回滚。

## 完成定义

- checklist 全完成，ruff + 全量 pytest 绿（含 C1/C2 及旧链路测试）
- FakeLLMClient 覆盖：单块、多块、续写、重试、取消、错误包装、prompt 快照
