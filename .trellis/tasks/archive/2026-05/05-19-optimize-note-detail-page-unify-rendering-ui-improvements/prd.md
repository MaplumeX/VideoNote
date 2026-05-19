# Optimize Note Detail Page — Unify Rendering & UI Improvements

## Goal

统一笔记详情页的渲染管线（去掉 react-markdown → HTML），始终使用 Milkdown WYSIWYG，同时重构布局为左操作栏+全宽内容+右侧 TOC 三栏。

## Requirements

* 去掉独立的预览模式，始终在 Milkdown WYSIWYG 中
* 去掉 react-markdown 及相关 rehype 依赖
* 重构布局：左侧窄栏放操作/标签/文件夹，中间全宽内容区，右侧 TOC
* 为 Milkdown 补全代码高亮、KaTeX 数学公式、Mermaid 图表支持
* 保持现有功能：时间戳徽章、TOC、下载、收藏、标签管理、文件夹

## Acceptance Criteria

* [ ] NotePreview.tsx 删除，NoteDetailPage 不再使用 react-markdown
* [ ] Milkdown 始终渲染，无预览/编辑切换按钮
* [ ] 三栏布局：左侧操作栏 | 中间 Milkdown | 右侧 TOC
* [ ] 代码高亮通过 @milkdown/plugin-prism 正常工作
* [ ] KaTeX 数学公式通过自定义 $node + $remark + remark-math + katex 渲染
* [ ] Mermaid 图表通过自定义 $node + $view + $remark 渲染
* [ ] 时间戳徽章正常
* [ ] TOC 正常（从 ProseMirror doc 或 DOM 提取 headings）
* [ ] Ctrl/Cmd+S 保存正常
* [ ] 切换笔记时编辑器正确重载
* [ ] 删除不再需要的依赖：react-markdown, @shikijs/rehype, rehype-slug, rehype-katex, shiki

## Definition of Done

* Lint / typecheck 通过
* 手动测试：保存、TOC、代码块高亮、$...$ 公式、$$...$$ 块公式、Mermaid 图表、时间戳徽章、标签、文件夹、下载、收藏

## Decision (ADR-lite)

**Context**: 笔记详情页有两套渲染管线（react-markdown 预览 + Milkdown 编辑），维护成本高且用户不希望转 HTML
**Decision**: 统一为 Milkdown WYSIWYG，去掉独立预览模式；布局改为三栏
**Consequences**: 需要为 Milkdown 补全代码高亮/数学/Mermaid 插件，但消除双管线维护负担

## Technical Approach

### 渲染统一
1. 删除 NotePreview.tsx 和 react-markdown 管线
2. Milkdown 补全插件：
   - **代码高亮**：`@milkdown/plugin-prism`（v7.21.1 兼容，基于 refractor，轻量无 Vue 依赖）
   - **KaTeX 数学**：自定义实现 — `$nodeSchema("math_inline")` + `$remark` 包装 `remark-math` + `katex.render()`，参照 Crepe latex feature 但无 Vue 依赖
   - **Mermaid 图表**：自定义 `$node("mermaid-diagram")` + `$view` + `$remark`，异步渲染，参照现有 timestamp-badge 模式
3. 删除不再需要的依赖：react-markdown, @shikijs/rehype, rehype-slug, rehype-katex, shiki

### 布局重构
- 左侧固定窄栏（w-56）：操作按钮（保存/下载/收藏）+ 标签 + 文件夹
- 中间 flex-1：Milkdown 编辑器全宽，去掉 max-w-3xl
- 右侧 w-52：TOC（保持现有实现，从 DOM 提取 headings）

### 只读模式
- 不再需要只读/编辑切换，Milkdown 始终可编辑
- 保存仍通过 Ctrl/Cmd+S

## Out of Scope

* Milkdown 代码块内的 CodeMirror 编辑体验（plugin-prism 只做高亮装饰，不做代码编辑）
* LaTeX 行内公式的编辑 tooltip（点击后直接编辑源码）
* Mermaid 代码块的编辑 UI（显示 SVG 预览 + 源码）

## Research References

* [`research/milkdown-plugins.md`](research/milkdown-plugins.md) — Milkdown v7 插件生态调研：plugin-prism 可用，plugin-math/plugin-diagram 已废弃需自定义，只读模式通过 editorViewOptionsCtx

## Technical Notes

* 关键文件：NoteDetailPage.tsx, NotePreview.tsx（删除）, NoteEditor.tsx, TableOfContents.tsx
* Milkdown v7 使用 $node/$view/$remark API 定义自定义节点
* TOC 当前通过 querySelectorAll("h2, h3") 扫描 DOM — 保持此方式（Milkdown 渲染后 DOM 中仍有 h2/h3）
* Mermaid 渲染是异步的，NodeView 需处理 async render
