# Add Video Thumbnail/Cover to Card View

## Goal

在卡片视图中显示视频封面缩略图，让用户在浏览历史记录和仪表盘时能直观地识别每个视频。

## Requirements

* 后端：从 yt-dlp `extract_info` 提取 `thumbnail` URL 并存储到数据库 `thumbnail_url` 列
* 后端：数据库 migration 新增 `thumbnail_url` 列（TEXT, nullable）
* 后端：`TaskListItem` schema 增加 `thumbnail_url` 字段
* 后端：创建任务时将 thumbnail_url 写入数据库
* 前端：`TaskItem` 类型增加 `thumbnail_url?: string`
* 前端：HistoryPage 卡片模式在卡片顶部显示缩略图
* 前端：DashboardPage 卡片在卡片顶部显示缩略图
* 前端：上传视频（无 thumbnail_url）显示带文件图标的占位图

## Acceptance Criteria

* [ ] 新建的 YouTube/Bilibili 视频任务，卡片视图中显示真实缩略图
* [ ] 上传视频的卡片显示占位图（文件图标 + 灰色背景）
* [ ] 已有任务（无 thumbnail_url 数据）不显示缩略图，不破坏布局
* [ ] lint / typecheck 通过

## Definition of Done

* Lint / typecheck 通过
* 现有功能无回归

## Technical Approach

1. **DB migration**: 新增 `thumbnail_url TEXT` 列到 tasks 表
2. **后端提取**: 在 `subtitle.py` 的 `extract_info` 调用后，取 `info["thumbnail"]` 存入数据库
3. **API 扩展**: `TaskListItem` / `TaskResponse` 增加 `thumbnail_url` 字段
4. **前端类型**: `TaskItem` 增加 `thumbnail_url?: string`
5. **卡片渲染**: Card 组件的第一个子元素为 `<img>` 或占位 `<div>`，利用已有 CSS（`has-[>img:first-child]:pt-0`）

## Decision (ADR-lite)

**Context**: 上传视频无外部缩略图 URL，需决定处理方式
**Decision**: 仅用占位图 — URL 视频显示真实缩略图，上传视频显示占位图
**Consequences**: 无需 ffmpeg 依赖和额外存储，后续可扩展

## Out of Scope

* 已有任务回填 thumbnail_url（后续可加）
* ffmpeg 生成上传视频缩略图
* 缩略图缓存/代理
* img onerror 回退处理
* 用户自定义封面

## Technical Notes

* 后端 yt-dlp `extract_info` 已返回 `info["thumbnail"]`
* 数据库 migration 路径：`backend/migrations/`
* Card 组件 CSS 已支持 `<img>` 作为第一个子元素
* 关键文件：`backend/app/db.py`, `backend/app/schemas.py`, `backend/app/services/subtitle.py`, `frontend/src/types/index.ts`, `frontend/src/pages/HistoryPage.tsx`, `frontend/src/pages/DashboardPage.tsx`
