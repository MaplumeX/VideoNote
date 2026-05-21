# Remove double-wrapping in note editor layout

## Goal

移除 NoteEditor 组件中不必要的双层 div 包裹，让笔记内容直接填充编辑区域，无边框、无 padding、无卡片感。

## Requirements

* 移除 NoteEditor 中的外层 `div.w-full` 和内层 `div.rounded-xl.border.p-6.milkdown-editor-wrapper`
* MilkdownProvider 直接放在页面级容器 `div.flex-1.min-w-0` 内
* 编辑器内容完全铺满编辑区域，无边框、无内边距
* MilkdownEditorInner 的 `div.relative`（slash menu 定位用）保留

## Acceptance Criteria

* [ ] NoteEditor 不再有双层 div wrapper
* [ ] 编辑器内容视觉上直接填充编辑区域（无边框、无 padding）
* [ ] Milkdown slash menu 定位仍正常工作
* [ ] 暗色模式下视觉正常

## Definition of Done

* Lint / typecheck / CI green
* 视觉无回归

## Decision (ADR-lite)

**Context**: 用户不喜欢笔记内容被包在带边框和 padding 的"卡片"内层里，觉得不必要
**Decision**: 完全铺满方案 — 去掉边框、圆角、padding，内容直接贴边
**Consequences**: 笔记内容会紧贴编辑区域边缘，视觉上更"平"

## Out of Scope

* MilkdownEditorInner 内部的 `div.relative` 改动（功能性，需保留）

## Technical Notes

* 关键文件：`frontend/src/components/NoteEditor.tsx` (line 504-510)
* `milkdown-editor-wrapper` 类无 CSS 定义，可安全移除
* MilkdownEditorInner 的 `div.relative`（line 461）用于 SlashProvider 定位，必须保留
