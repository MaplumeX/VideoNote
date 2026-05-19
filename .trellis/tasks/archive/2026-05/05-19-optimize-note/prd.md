# Optimize Note Feature

## Goal

为 VideoNote 添加笔记编辑（WYSIWYG）、标签+文件夹组织、Markdown 渲染全量增强（代码高亮/TOC/KaTeX/Mermaid/主题），将笔记从只读 AI 产物升级为可编辑、可组织的个人知识库。

## Requirements

### 编辑 (WYSIWYG)

* 笔记生成后可原地编辑，WYSIWYG 所见即所得模式
* 编辑器加载现有 Markdown 内容，编辑后保存回 Markdown（无损往返）
* 保留 TimestampBadge（`[HH:MM:SS](#t=SECONDS)`）在编辑器中的渲染
* Slash 命令菜单（Notion 风格）
* GFM 支持（表格、任务列表、删除线）
* 中文输入无 bug

### 组织 (Tags + Folders)

* 标签：多对多，用户可创建/重命名/删除标签
* 文件夹：adjacency list 树状结构，笔记属于最多一个文件夹
* 收藏：星标收藏笔记
* 历史页支持按标签/文件夹/收藏筛选
* 新建笔记时可选文件夹和标签
* 标签支持按名称自动创建（Notion 风格）

### 预览增强 (Markdown Enhancement)

* 代码语法高亮（Shiki，双主题 light/dark）
* TOC 侧边栏目录导航（rehype-slug + 自定义组件）
* KaTeX 数学公式渲染（`$...$` / `$$...$$`）
* Mermaid 图表渲染（懒加载）
* 暗/亮主题切换（CSS 变量 + Shiki 双主题 + Mermaid theme）

## Acceptance Criteria

* [ ] 笔记详情页可切换编辑/阅读模式，编辑后保存 Markdown 无损
* [ ] 编辑器中 TimestampBadge 正常渲染且不破坏 Markdown 往返
* [ ] Slash 命令菜单可用
* [ ] 可创建/重命名/删除标签，标签可关联到笔记
* [ ] 可创建/移动/删除文件夹（含子文件夹），笔记可移入文件夹
* [ ] 可收藏/取消收藏笔记
* [ ] 历史页可按标签、文件夹、收藏筛选
* [ ] 代码块有语法高亮，主题切换时高亮颜色跟随
* [ ] TOC 侧边栏显示标题列表，点击跳转到对应位置
* [ ] `$E=mc^2$` 和 `$$...$$` 正确渲染为数学公式
* [ ] ` ```mermaid ` 代码块渲染为图表
* [ ] 暗/亮主题切换后，所有渲染元素（代码、公式、图表、正文）颜色正确

## Definition of Done

* Tests added/updated (unit/integration where appropriate)
* Lint / typecheck / CI green
* Rollout: 新增功能均为增量（无 breaking change），回滚只需前端回退
* PRAGMA foreign_keys = ON 修复（现有 FK 约束生效）

## Out of Scope

* 视频播放器 / 时间戳跳转（独立任务）
* 多人协作编辑
* 文件夹拖拽排序
* 笔记全文搜索
* 笔记导出格式扩展（PDF/HTML 等）
* 笔记分享

## Decision (ADR-lite)

**Context**: 需要选择 WYSIWYG Markdown 编辑器、Markdown 增强插件栈、标签+文件夹数据模型

**Decision**:
1. **编辑器**: Milkdown（Markdown-first、CJK 无已知 bug、~700KB、可扩展 TimestampBadge 自定义节点）
2. **增强栈**: `@shikijs/rehype` + `rehype-slug` + `remark-math` + `rehype-katex` + 自定义 Mermaid React 组件（懒加载）
3. **数据模型**: tags + note_tags junction table + folders adjacency list + is_favorite 布尔列

**Consequences**:
- Milkdown Crepe（Notion 风 UI）有 Vue 依赖，需自建 Notion 风格 UI 或使用核心插件子集
- Mermaid ~2-3MB gzipped，必须懒加载
- 需修复 PRAGMA foreign_keys = ON（现有 FK 约束之前未生效）

## Research References

* [`research/wysiwyg-editor.md`](research/wysiwyg-editor.md) — WYSIWYG 编辑器对比（Milkdown/Tiptap/BlockNote/Cherry/ByteMD）
* [`research/markdown-enhancement.md`](research/markdown-enhancement.md) — Markdown 增强插件栈（Shiki/TOC/KaTeX/Mermaid/主题）
* [`research/tags-folders-schema.md`](research/tags-folders-schema.md) — 标签+文件夹 schema 设计、API 设计、迁移策略

## Technical Notes

### 前端

* 关键文件：NoteView.tsx → 拆分为 NoteEditor（Milkdown）+ NotePreview（react-markdown 增强）
* Milkdown 自定义 ProseMirror Mark/Node 实现 TimestampBadge
* react-markdown 保留用于只读预览模式，增加 rehype/remark 插件
* `@tailwindcss/typography` 需确认 Tailwind 4 兼容性
* Shiki WASM 在 Vite 中加载，可用 `@shikijs/engine-javascript` 替代避免 WASM

### 后端

* 新增 3 张表：tags, folders, note_tags
* tasks 表新增 3 列：folder_id, is_favorite, favorited_at
* 新增 API 路由：/api/folders/*, /api/tags/*, /api/tasks/{id}/tags, /api/tasks/{id}/folder, /api/tasks/{id}/favorite
* GET /api/tasks 增加 folder/tag/is_favorite 筛选参数
* 修复 PRAGMA foreign_keys = ON（需重构数据库连接为共享 helper）
* 笔记编辑：PUT /api/tasks/{id}/content 更新 result_json 中的 markdown

### 迁移

* 所有变更为增量（3 新表 + 3 新列），无需数据回填
* 沿用 init_db() 中 ALTER TABLE + try/except 模式
