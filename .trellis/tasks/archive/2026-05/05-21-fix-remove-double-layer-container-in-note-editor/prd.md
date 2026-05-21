# Fix: Remove double-layer container in note editor

## Goal

消除笔记编辑区"容器内还有一个容器"的双层视觉效果，去掉 prose max-width 限宽，让内容撑满外层卡片。

## What I already know

* NoteEditor 外层容器（第504行）有 `rounded-xl border border-border bg-background p-6`，形成一个带圆角边框的卡片
* 页面本身也是 `bg-background`，同色背景 + 边框 = 视觉上的"卡片中的卡片"
* nord 主题（`@milkdown/theme-nord/lib/index.js`）自动给 ProseMirror EditorView 注入 class `prose dark:prose-invert milkdown-theme-nord`
* `prose` class 来自 `@tailwindcss/typography`，会设置 `max-width: 65ch` 和额外的 margin/padding，形成编辑内容区的"第二层容器"效果
* 完整嵌套：页面背景 → 圆角边框卡片(p-6) → prose(max-width:65ch + margin) → 编辑内容

## Requirements

* 保留外层卡片（rounded-xl border border-border bg-background p-6）
* 覆盖 `prose` 的 max-width 限宽，让编辑内容撑满卡片宽度
* 消除双层容器的视觉感
* 亮色和暗色模式下均正常

## Acceptance Criteria

- [ ] 编辑区不再有 prose max-width 导致的"内嵌小容器"效果
- [ ] 编辑内容宽度与卡片宽度一致
- [ ] 亮色和暗色模式下均正常
- [ ] 编辑器排版/可读性不降级

## Definition of Done

* Lint / typecheck / CI green
* 视觉验证

## Decision (ADR-lite)

**Context**: 编辑区有双层容器感 — 外层卡片 + 内层 prose max-width
**Decision**: 保留外层卡片，去掉内层 prose 的 max-width 限宽（用户选择方案2）
**Consequences**: 内容会撑满卡片宽度，排版宽度由卡片宽度控制而非 prose

## Out of Scope

* 不改动 Milkdown 主题包本身（node_modules）
* 不改动 TOC / 侧边栏等其他布局
* 不修改外层卡片的样式

## Technical Notes

* 关键文件：`frontend/src/components/NoteEditor.tsx` 第504行
* nord 主题注入 `prose` class 是在 `editorViewOptionsCtx` 中
* `prose` 的 max-width 可通过自定义 CSS `.milkdown-theme-nord.prose { max-width: none; }` 覆盖
* 也可通过 Tailwind 的 `max-w-none` modifier，但 nord 主题是动态注入 class 的，需要在 CSS 层面处理
