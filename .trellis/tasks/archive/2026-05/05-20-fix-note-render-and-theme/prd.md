# Fix Note Rendering and Theme

## Goal

修复 Milkdown 编辑器中标题/加粗等 Markdown 格式不渲染（显示原始 `##`、`**`）的问题，以及编辑器在切换主题时始终显示暗色模式样式的问题。

## What I already know

* **根因 1 — Nord 主题 CSS 包含完整的 Tailwind v4 重置层**：`@milkdown/theme-nord/style.css` 自带 `@layer base` 重置，其中 `h1-h6 { font-size: inherit; font-weight: inherit; }` 和 `ol,ul,menu { list-style: none; }` 覆盖了项目自身的 Tailwind 样式，导致标题无字号/字重差异、列表无标记
* **根因 2 — Nord 暗色模式用 `prefers-color-scheme` 而非 `.dark` class**：Nord CSS 中暗色适配全部用 `@media (prefers-color-scheme: dark)` 媒体查询，项目用手动 `.dark` class 切换主题，二者不匹配
* **附带问题 — Prism 主题仅亮色**：`prismjs/themes/prism.css` 无暗色适配，代码块语法高亮在暗色模式下颜色不对
* **附带问题 — KaTeX 硬编码黑色文字**：`katex/dist/katex.min.css` 用硬编码黑色文字，暗色模式下数学公式不可读
* **Orphan CSS**：`index.css` 中 `.dark .prose` 覆盖规则（155-173 行）是旧 `NotePreview` 的残留，Milkdown 编辑器不用 `prose` class
* 编辑器使用 `milkdown-theme-nord` class 作为主题标识，wrapper div 使用 `milkdown-editor-wrapper` class
* 项目使用 Tailwind v4 + CSS 自定义属性（oklch），暗色模式通过 `document.documentElement.classList.add("dark")` 切换

## Requirements

* 编辑器内标题 h1-h6 必须显示正确的字号和字重（所见即所得）
* 加粗文本必须显示粗体
* 列表必须显示列表标记（disc / decimal）
* 切换主题时编辑器内容区域必须正确适配亮/暗色
* 代码块语法高亮在暗色模式下可读
* KaTeX 数学公式在暗色模式下可读

## Acceptance Criteria

- [ ] 标题 h1-h6 有可见的字号和字重差异
- [ ] `**bold**` 渲染为粗体
- [ ] 有序列表和无序列表有正确的列表标记
- [ ] 亮色模式下编辑器内容区域背景为亮色、文字为深色
- [ ] 暗色模式下编辑器内容区域背景为暗色、文字为亮色
- [ ] 切换主题后编辑器样式即时响应
- [ ] 代码块语法高亮在两种模式下可读
- [ ] KaTeX 公式在两种模式下可读
- [ ] `tsc --noEmit` 无新增错误
- [ ] `eslint` 无新增错误

## Definition of Done

* 上述 Acceptance Criteria 全部通过
* 无 orphan CSS（清理旧的 `.dark .prose` 规则）
* 本地 `cd frontend && npx vite build` 成功

## Out of Scope

* 只读/预览模式（编辑器始终可编辑，不需要 preview 模式）
* Mermaid 图表暗色适配（已有实现）
* Slash 命令菜单样式修改
* 编辑器功能增强（新插件、新节点类型等）

## Decision (ADR-lite)

**Context**: Nord 主题 CSS 自带 Tailwind v4 重置层覆盖全局样式，暗色模式用 prefers-color-scheme 与项目 .dark class 不兼容
**Decision**: 采用方案 A — 不导入 Nord style.css，在 index.css 中自写 .milkdown-theme-nord 样式，使用项目 CSS 变量，暗色适配走 .dark class
**Consequences**: 完全控制编辑器样式，与项目主题系统一致；需要手动维护编辑器排版样式（Nord 升级不会自动带来样式变更，但这也是优点——避免意外覆盖）

## Technical Notes

### 关键文件

* `frontend/src/components/NoteEditor.tsx` — Milkdown 编辑器主组件，import Nord style.css
* `frontend/src/index.css` — 全局样式，包含 `.dark .prose` 残留和 Tailwind 变量
* `frontend/src/hooks/useTheme.tsx` — 主题切换，操作 `document.documentElement.classList`

### Nord style.css 分析

* 完整的 Tailwind v4 `@layer base` 重置（行 71-316），覆盖 h1-h6、ol/ul、a、strong 等元素样式
* `@layer components` 为空
* `@layer utilities` 仅 `.block/.hidden/.inline/.table/.transform`
* `.milkdown-theme-nord` 下有完整的排版样式（h1-h6 字号字重、列表样式、代码块样式等）
* 暗色模式使用 `@media (prefers-color-scheme: dark)` 媒体查询

### 可行方案

**方案 A — 自定义编辑器样式（推荐）**

* 不导入 `@milkdown/theme-nord/style.css`，只使用 Nord 的 JS 主题配置（`nord` 函数传给 `.config(nord)`）
* 在 `index.css` 中新建 `.milkdown-theme-nord` 样式规则，直接使用项目的 CSS 自定义属性（`--color-foreground`、`--color-muted` 等）
* 暗色适配使用 `.dark .milkdown-theme-nord` 选择器，与项目主题系统一致
* Prism 改为条件导入：亮色用 `prism.css`，暗色用 `prism-tomorrow.css`（或用 CSS 覆盖）
* KaTeX 暗色用 CSS 覆盖 `.dark .katex` 颜色

**方案 B — 覆盖 Nord CSS 冲突部分**

* 保留 `@milkdown/theme-nord/style.css` 导入
* 在 `index.css` 中用更高特异性覆盖 Nord 的 `@layer base` 重置（如 `:where(.milkdown-theme-nord) h1 { ... }`）
* 用 `.dark .milkdown-theme-nord` 覆盖暗色模式
* 问题：Nord 的 `@layer base` 重置影响全局，需要大量覆盖，维护成本高

**方案 C — 使用 Crepe 主题替代 Nord**

* Milkdown 提供了 `@milkdown/crepe` 包，自带亮/暗主题切换（`nord` / `nord-dark` / `crepe` / `crepe-dark` 等）
* 根据 `.dark` class 动态切换 Crepe 主题
* 问题：Crepe 是更高层的封装，API 不同于当前 `@milkdown/theme-nord`，迁移工作量大
