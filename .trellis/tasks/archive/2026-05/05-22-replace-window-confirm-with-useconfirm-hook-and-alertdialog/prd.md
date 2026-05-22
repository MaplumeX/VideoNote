# Replace window.confirm with useConfirm hook and AlertDialog

## Goal

用自定义的 `useConfirm` hook + shadcn AlertDialog 替换项目中所有 `window.confirm` 调用，消除原生弹窗，获得与项目 UI 风格一致的确认对话框，同时保持调用侧代码改动最小。

## What I already know

* 5 处 `window.confirm` 调用：
  - `HistoryPage.tsx:315` — `handleDelete` (单个删除)
  - `HistoryPage.tsx:327` — `handleRetry` (重试)
  - `HistoryPage.tsx:340` — `handleCancel` (取消任务)
  - `HistoryPage.tsx:388` — `handleBatchDelete` (批量删除，带 count 插值)
  - `ContentSidebar.tsx:125` — `handleDeleteTag` (删除标签，带 name 插值)
  - `ContentSidebar.tsx:139` — `handleDeleteFolder` (删除文件夹，带 name 插值)
* 技术栈：React 19 + shadcn/ui (base-nova 风格, 基于 @base-ui/react) + Tailwind + lucide-react + react-i18next
* 项目中尚无 AlertDialog 组件（shadcn/ui 有标准组件可 `npx shadcn@latest add alert-dialog`）
* Sheet 组件已用 `@base-ui/react/dialog` 构建，AlertDialog 同理，无需引入 Radix
* 项目中已有 Context Provider 模式：`ThemeProvider` 用 `createContext` + `useContext`
* AppLayout 是全局布局根节点，已有 `ThemeProvider` 和 `TooltipProvider`
* 所有使用 `window.confirm` 的 handler 都已是 `async` 函数

## Requirements

* 新增 `useConfirm` hook，API 为 `confirm({ title, description?, destructive? }) => Promise<boolean>`
* 新增 shadcn AlertDialog 组件（`npx shadcn@latest add alert-dialog`，基于 @base-ui/react）
* 新增 `ConfirmProvider` 组件，包裹在 AppLayout 中
* 替换所有 5 处 `window.confirm` 调用
* 保持 i18n 翻译键不变

## Acceptance Criteria

* [ ] 项目中无任何 `window.confirm` 调用
* [ ] 点击确认/取消按钮后 AlertDialog 正确关闭，返回 true/false
* [ ] 支持 title（必填）和可选 description
* [ ] 支持 i18n 插值参数（如 count、name）——通过 title/description 字符串传入
* [ ] destructive 操作确认按钮使用 destructive variant 视觉区分
* [ ] 所有已有 i18n 翻译键继续工作

## Definition of Done

* Lint / typecheck / CI green
* 所有 `window.confirm` 已移除
* 手动验证确认/取消流程正常

## Technical Approach

1. `npx shadcn@latest add alert-dialog` — 生成 `components/ui/alert-dialog.tsx`
2. 创建 `hooks/useConfirm.tsx` — ConfirmProvider + useConfirm hook
   - ConfirmProvider 内部持有 state（title, description, destructive, resolve callback）
   - `confirm()` 调用时 setState + return new Promise；按钮点击时 resolve(true/false) + 清除 state
   - 渲染 AlertDialog，destructive 时确认按钮用 `variant="destructive"`
3. 在 `AppLayout.tsx` 中将 `<ConfirmProvider>` 包裹在现有 Provider 内层
4. 逐一替换 5 处 `window.confirm`：`if (!window.confirm(t(...))) return` → `if (!await confirm({ title: t(...), destructive: true })) return`

## Decision (ADR-lite)

**Context**: 需要选择 `useConfirm` 的 API 风格
**Decision**: 极简对象式 `confirm({ title, description?, destructive? })`
**Consequences**: 调用侧最简洁，未来可扩展字段（如 confirmText/cancelText）无需改签名

## Out of Scope

* 确认弹窗队列（并发场景）
* 非确认类的模态框（如表单弹窗）
* 自定义确认/取消按钮文案（使用默认 i18n 即可）
* 其他未使用 window.confirm 的页面

## Technical Notes

* AppLayout 是 Provider 的挂载点（line 49-78: ThemeProvider + TooltipProvider）
* 所有 handler 已是 async，改为 `await confirm(...)` 无需额外改动
* shadcn base-nova 风格的 AlertDialog 基于 @base-ui/react/dialog，与 Sheet 一致，不引入 Radix
