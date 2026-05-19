# 优化新建笔记界面 UI 布局

## Goal

改善 `/app/new` 页面的视觉体验和交互流程，使其从当前的"单输入框"观感升级为有引导感、视觉层次分明、进度反馈清晰的专业界面。

## What I already know

* 当前 NewNotePage 是 `max-w-xl` 居中布局，内容仅为 tab 切换器 + URL 输入框/拖拽区
* 处理中显示 ProgressBar（Card 内的百分比条 + 阶段文字）
* 外层 AppLayout 已提供 `max-w-5xl` 容器 + sidebar，NewNotePage 可用空间充足
* 技术栈：React 19 + TypeScript + shadcn/ui + Tailwind v4 + react-dropzone + i18next
* i18n 已配置中英文，所有新增文案需同步更新两个 locale 文件

## Assumptions (temporary)

* 4 个优化方向都需要实现
* Hero 区域文案可复用 i18n 中已有的 `app.title` / `app.subtitle`
* 合并 URL 和上传视图后，不再需要 tab 切换
* 步骤指示器替换现有 ProgressBar 的百分比条样式

## Open Questions

_(none)_

## Decisions

* **Hero 风格** → 简约大标题（粗体大字 + 浅色副标题，无装饰图，Notion/Linear 风格）
* **合并视图顺序** → URL 输入在上，文件上传区在下
* **步骤指示器粒度** → 精简 3 阶段：下载（downloading + extracting_subtitles）→ 转录（transcribing）→ 生成笔记（generating_notes）；pending/failed/cancelled 用特殊状态处理

## Requirements (evolving)

* R1: 增加 Hero 区域（粗体大标题 + 浅色副标题，无装饰图，简约 Notion/Linear 风格），提升页面着陆感
* R2: 合并 URL 输入和文件上传到一个视图，URL 在上、上传在下，去掉 tab 切换
* R3: 丰富拖拽区视觉（图标、动画、hover/drag 状态）
* R4: 进度体验升级为 3 阶段步骤指示器：下载 → 转录 → 生成笔记（pending 作为初始态，failed/cancelled 用错误状态）
* R5: NoteDetailPage 中进行中笔记的进度也使用步骤指示器，与 NewNotePage 保持一致

## Acceptance Criteria (evolving)

* [ ] 页面顶部有清晰的标题和副标题
* [ ] URL 输入和文件上传同时可见，无需切换 tab
* [ ] 拖拽区视觉丰富，drag-active 状态有明显反馈
* [ ] 进度显示为 3 阶段步骤指示器，各阶段清晰可辨
* [ ] NoteDetailPage 中进行中笔记的进度也使用步骤指示器（与 NewNotePage 一致）
* [ ] 中英文 i18n 同步更新
* [ ] 现有功能（URL 提交、文件上传、进度追踪、自动跳转）不受影响

## Definition of Done

* Lint / typecheck 通过
* 现有功能无回归
* 深色/浅色主题均正常

## Out of Scope

* 双栏布局（方向 5）
* 过渡动画（方向 6）
* 后端逻辑变更

## Technical Notes

* 核心文件：`NewNotePage.tsx`, `VideoInput.tsx`, `ProgressBar.tsx`
* 关联文件：`NoteDetailPage.tsx`（也使用 ProgressBar，需同步升级为步骤指示器）
* 布局容器：`AppLayout.tsx` 提供 `max-w-5xl` + `px-4 py-8`
* i18n 文件：`frontend/src/i18n/locales/en.json`, `zh-CN.json`
* shadcn/ui 组件可用：Card, Button, Input, Badge, Select, Separator, DropdownMenu
