# 子任务 C5：前端契约适配

## Goal

按 C1 契约文档与 C4 落地的新 SSE/API 端点，适配前端类型与进度 UI，使应用在新契约下完整可用。

## Dependencies

- 依赖 C4（pipeline-orchestrator）落地的新 SSE/REST 契约。
- 引用 C1 产出的契约文档（阶段枚举、事件 schema）。

## Scope

- `frontend/src/types/index.ts`：新 `TaskStage` 枚举、进度载荷类型（stage + phase_progress + message + attempt + timestamp）。
- `frontend/src/hooks/useSSE.ts`：事件解析与状态更新适配新载荷；保留断线重连/心跳语义。
- `frontend/src/components/StepIndicator.tsx`：步骤与新阶段一一对应，阶段内 fraction 渲染；failed/cancelled 只标红发生阶段及其后（保留历史修复语义）。
- `frontend/src/components/StatusBadge.tsx` / `ProgressBar.tsx`：新枚举映射；进度条改为阶段内进度或双级展示（以 C1 契约为准）。
- `frontend/src/pages/NewNotePage.tsx`：进度消息实时展示（保留历史修复语义）。
- i18n：新阶段/错误码的文案 key（en / zh-CN）。

## Acceptance Criteria

- [ ] `npm test -- --run` 全绿（含 useSSE/sseParser/StepIndicator 相关测试更新）。
- [ ] `npm run build` 通过，无 TS 类型错误。
- [ ] 手动验收：提交任务 → 步骤指示器按新阶段推进、消息实时、进度单调；失败只标红对应阶段；取消后 UI 即时反映。
- [ ] i18n 双语无缺 key。

## Notes

- 不涉及 Milkdown 编辑器、笔记管理、设置页逻辑（仅当类型引用连带变化时做最小调整）。
