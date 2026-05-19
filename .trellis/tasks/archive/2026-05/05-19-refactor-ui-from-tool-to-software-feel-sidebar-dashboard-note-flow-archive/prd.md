# Refactor UI: From Tool to Software Feel

## Goal

将 VideoNote 从"用完即走的在线工具"改造为"有空间感的在线软件"，通过侧边栏导航、Dashboard 首页、独立笔记详情页和卡片化历史归档四个核心改动，建立用户驻留感。

## What I already know

* 当前布局：顶部 header 5个按钮（新建/历史/设置/语言/退出），无侧边栏，内容 max-w-5xl 居中
* 主应用 VideoNoteApp 使用 3 步状态机：input → processing → result，同页面切换
* HistoryPage 是扁平列表，点击完成的任务通过 `?task=` query param 在首页展示结果
* 后端 API：GET /tasks（分页列表）、GET /tasks/{id}/result（markdown+title）、GET /tasks/{id}/progress（SSE）
* TaskItem 字段：job_id, stage, progress, message, created_at, video_url, file_name, platform, language, source_type
* NoteResponse 字段：job_id, markdown, title
* 技术栈：React 19 + TypeScript + Tailwind v4 + react-router v7 + lucide-react + cn() 工具函数
* 无现成 UI 组件库，基于 shadcn 模式（cva + clsx + tailwind-merge）手写组件
* i18n：中英双语

## Decisions

### D1: 侧边栏风格 — 窄图标+文字（Notion/Linear 风格）

* 宽约 200px，图标+文字竖排，左侧固定
* 导航项：新建笔记、历史记录、设置
* 底部区域：语言切换、退出登录
* 桌面端始终可见，移动端汉堡菜单触发抽屉

### D2: Dashboard 内容 — 最近笔记卡片 + 醒目新建按钮

* 取最近 5 条任务（不论状态），卡片显示标题/来源/日期/状态
* 完成的可直接点击进入详情
* 醒目的"新建视频笔记"按钮
* 不做统计模块

### D3: 笔记详情页 — 全宽笔记视图

* 路由：/app/notes/:id
* 顶部面包屑（返回历史）+ 操作栏（下载 Markdown）
* 主内容区全宽展示笔记 markdown
* 无双栏布局

### D4: 历史归档 — 2列网格卡片

* Notion 风格卡片网格，每张显示标题（截断）、来源平台图标、日期、状态徽章
* hover 微提升效果
* 点击完成的任务进入详情页
* 分页保持

### D5: 新建笔记流程 — 独立路由 /app/new

* 侧边栏点击"新建"进入独立页面
* 输入/上传后开始处理，SSE 后台继续
* 处理中可导航到其他页面（不阻塞）
* 处理完成后自动跳转到 /app/notes/:id

## Requirements

* 1. 侧边栏导航：~200px 宽，图标+文字，导航项（新建/历史/设置），底部（语言/登出），移动端抽屉
* 2. Dashboard 首页（/app）：最近5条任务卡片 + 醒目新建按钮
* 3. 新建笔记（/app/new）：独立路由，后台处理不阻塞，完成后跳转详情页，离开再回来通过 URL param 恢复 SSE 进度
* 4. 笔记详情页（/app/notes/:id）：全宽 markdown，顶部面包屑+操作栏
* 5. 历史归档（/app/history）：2列网格卡片，状态徽章，点击进入详情
* 6. 移除当前 AppLayout header 按钮行
* 7. 移除当前 3 步状态机同页面切换逻辑

## Acceptance Criteria

* [ ] 侧边栏含所有导航项，桌面端固定，移动端抽屉
* [ ] /app 显示 Dashboard（最近5条卡片+新建按钮）
* [ ] /app/new 可提交 URL/上传文件，处理中可离开页面，回来通过 URL param 恢复 SSE 进度
* [ ] /app/notes/:id 展示笔记 markdown，面包屑+下载
* [ ] /app/history 以2列网格卡片展示，完成的可点击进入详情
* [ ] 所有现有功能不丢失（输入/处理/结果/历史/设置/语言/登出）
* [ ] 中英双语 i18n 更新

## Definition of Done

* Lint / typecheck 通过
* 现有功能无回归
* 中英双语 i18n 更新
* 移动端基本可用

## Out of Scope

* 品牌 Logo/插图设计（仅布局结构改造）
* 页面过渡动画
* 色彩体系扩展
* 空状态插图
* 后端新增统计 API

## Technical Notes

* 关键文件：AppLayout.tsx（布局重构）、App.tsx（状态机拆除）、main.tsx（路由重构）、HistoryPage.tsx（卡片化）
* 后端 TaskListItem 不含 title 字段 → 卡片展示需考虑：方案A 在列表页单独请求 title，方案B 后端 TaskListItem 加 title 字段
* 侧边栏组件：新建 Sidebar.tsx
* Dashboard 组件：新建 DashboardPage.tsx
* 新建页组件：新建 NewNotePage.tsx
* 详情页组件：新建 NoteDetailPage.tsx
* 当前 VideoNoteApp 的 SSE/handleSubmit/handleUpload 逻辑迁移到 NewNotePage
* 当前 App.tsx 中 `?task=` query param 逻辑迁移到 NoteDetailPage
* /app/new 进度恢复：提交后 URL 变为 /app/new?job={jobId}，回来时检测 param 重新订阅 SSE
