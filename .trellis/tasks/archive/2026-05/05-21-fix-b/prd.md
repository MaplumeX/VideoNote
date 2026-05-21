# fix: B站视频封面因反盗链无法显示

## Goal

让B站视频封面能正常显示，绕过其CDN的Referer反盗链检查。

## Requirements

* 后端在任务创建时下载封面图片到本地（UPLOAD_DIR/thumbnails/）
* DB中 thumbnail_url 改存本地文件名而非外部URL
* 提供代理API端点 `GET /api/thumbnails/{filename}` 让前端加载封面
* 前端从代理端点加载而非直接加载外部URL
* 下载时携带 Referer 头绕过B站反盗链

## Acceptance Criteria

* [ ] B站视频封面在Dashboard和History页面正常显示
* [ ] YouTube封面仍然正常显示（不回退）
* [ ] 上传类型视频不受影响（仍显示占位图标）
* [ ] 下载失败时优雅降级（thumbnail_url 为 null，前端显示占位）

## Definition of Done

* Lint / typecheck 通过
* 手动验证B站封面可显示

## Decision (ADR-lite)

**Context**: B站CDN做Referer检查，前端直接加载外部URL会403
**Decision**: 任务创建时下载封面到本地，前端走后端代理API加载
**Consequences**: 多一层存储和API，但彻底解决反盗链问题，且对YouTube等无Referer限制的平台同样兼容

## Out of Scope

* 历史任务封面回填
* 封面缓存过期/刷新策略

## Technical Approach

1. `subtitle.py` 新增 `download_thumbnail(url) -> str | None`：用 httpx 下载图片，B站URL携带 `Referer: https://www.bilibili.com`，存入 `UPLOAD_DIR/thumbnails/`，返回本地文件名
2. `routes.py` 在调用 `get_video_info` 后，调用 `download_thumbnail`，将返回的本地文件名传给 `create_task`
3. `routes.py` 新增 `GET /api/thumbnails/{filename}` 端点，用 FileResponse 返回图片
4. 前端 thumbnail_url 拼接为 `/api/thumbnails/{value}` 加载

## Technical Notes

* 关键文件：backend/app/services/subtitle.py, backend/app/api/routes.py, frontend/src/pages/DashboardPage.tsx, frontend/src/pages/HistoryPage.tsx
* 存储：UPLOAD_DIR / thumbnails/ 目录
* httpx 已是项目依赖
