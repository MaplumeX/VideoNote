# 执行计划：C5 前端契约适配

## Checklist（有序）

- [ ] 1 `types/index.ts`：TaskStatus/TaskPhase 新枚举、TaskProgress/TaskItem 新字段、删旧 TaskStage
- [ ] 2 `components/StatusBadge.tsx` / `ProgressBar.tsx`：status 判断 + 阶段合成进度条
- [ ] 3 `components/StepIndicator.tsx`：phase → 步骤状态映射（URL/上传双路径、failed 标红范围、subtitle 跳级）
- [ ] 4 `hooks/useSSE.ts`：新载荷类型、终止判断改 status
- [ ] 5 `pages/NewNotePage.tsx` / `DashboardPage.tsx` / `HistoryPage.tsx` / `NoteDetailPage.tsx`：stage→status/phase 迁移
- [ ] 6 `api/client.ts`：TASK_MESSAGE_ERROR_CODES 增补（SUBTITLE_EXTRACTION_FAILED、TASK_CANCELLED）；translateTaskMessage 不变
- [ ] 7 i18n：en/zh-CN 的 progress.* 按 phase 重写 + 新错误码 key；删旧 key 前 grep 零引用确认
- [ ] 8 测试更新：StepIndicator/useSSE/NewNotePage/client 各测试文件
- [ ] 9 `npm test -- --run` 全绿 + `npm run build` 通过 + tsc 无错

## 验证命令

```bash
cd frontend
npm test -- --run
npm run build
```

## 边界与禁止事项

- 禁止修改 `backend/` 任何文件。
- 契约以 `docs/pipeline-contract.md` §2.1（SSE 载荷）与 §2.4（REST 模型变更表）为准，零漂移。
- 不改 sseParser.ts 解析核心（测试锁定行为）；编辑器/笔记管理/设置页零改动（类型连带最小调整除外）。

## 风险与回滚

- 遗漏某个 `.stage` 引用点 → tsc 全量编译兜底（删类型后所有引用点必然报错，物理上无法漏）。
- 全部为前端改动，revert 单 commit 即回滚。

## 完成定义

- checklist 全完成；前端测试与 build 全绿
- 手动验收：提交任务 → 步骤指示器按新 phase 推进、消息实时、进度单调合成；失败标红对应步骤；取消后 UI 即时反映（G4 门禁材料）
