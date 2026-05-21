# Remove double-layer wrapping in NoteEditor

## Goal

消除 NoteEditor 组件中笔记内容区域的冗余双层 div 包裹，简化 DOM 结构。

## What I already know

* NoteEditor.tsx 第 504-505 行有两层嵌套 div：
  * 外层: `<div className="w-full">` — 仅提供全宽度
  * 内层: `<div className="rounded-xl border border-border bg-background p-6 milkdown-editor-wrapper">` — 提供卡片视觉效果（圆角、边框、背景、内边距）
* `milkdown-editor-wrapper` 类名没有任何 CSS 样式规则引用，是纯标记性 class
* 上层布局链：AppLayout (`max-w-5xl mx-auto px-4 py-8`) → NoteDetailPage (`flex-1 min-w-0`) → NoteEditor 双层 div
* MilkdownEditorInner 内部还有一个 `<div className="relative">` 用于斜杠菜单定位，这是功能性的

## Assumptions (temporary)

* 外层 `w-full` div 是冗余的，因为父容器已经是 `flex-1 min-w-0`
* 用户希望简化包裹结构

## Decision (ADR-lite)

**Context**: NoteEditor 返回双层 div，外层仅 `w-full`，内层承载卡片样式。父容器已是 `flex-1 min-w-0`，外层冗余。
**Decision**: 合并为单层 div，将卡片样式（`rounded-xl border border-border bg-background p-6`）移至外层，移除 `w-full`（冗余）和 `milkdown-editor-wrapper`（无 CSS 引用）。
**Consequences**: DOM 层级减少一层，视觉表现不变。

## Requirements

* 消除 NoteEditor 返回值中的冗余双层 div
* 保留卡片视觉样式（圆角、边框、背景、内边距）

## Acceptance Criteria

* [ ] NoteEditor 返回单个 div 包裹编辑器，无冗余外层
* [ ] 卡片样式（圆角、边框、padding）保留
* [ ] tsc / eslint / build 通过

## Definition of Done

* Lint / typecheck / build green
* 视觉验证

## Out of Scope (explicit)

* MilkdownEditorInner 内部的 `relative` 定位 div（功能性，不动）
* AppLayout / NoteDetailPage 的布局结构调整

## Technical Notes

* 关键文件：`frontend/src/components/NoteEditor.tsx` (lines 503-511)
* `milkdown-editor-wrapper` 无 CSS 引用，可安全移除
