# 丰富视频处理等待体验：视频信息卡片 + 交互增强

## Goal

在视频处理等待界面（NewNotePage 和 NoteDetailPage 的 processing 状态）展示视频封面、标题等元数据，并增加取消等交互操作，让用户在等待时不再只盯着三个转圈圈，而是有内容可看、有操作可做。

## What I already know

- 当前进度界面仅有 `StepIndicator`（三步指示器 + 百分比），无任何视频元数据
- SSE 流只推送 `stage`/`progress`/`message`，不含视频元数据
- 后端在 `create_task()` 时已有 `thumbnail_url`（URL 类型任务）
- 后端通过 `get_video_info()` 获取 `title`，但只在任务完成时存入 `result_json`
- `create_task()` 不接受 `title` 参数，DB 的 tasks 表也没有 `title` 列
- 已有 `POST /tasks/{job_id}/cancel` 端点，但前端处理页面没有取消按钮
- 已有 `POST /tasks/{job_id}/retry` 端点，但仅对失败任务生效
- `ProgressBar` 组件已存在但未使用
- `TaskListItem` schema 有 `thumbnail_url` 字段，但 SSE 不推送这些信息
- 文件上传类型任务没有 thumbnail 和 video_url

## Assumptions (resolved)

- ~~title 需要新增为 tasks 表的独立列~~ → 已确认，需新增 title 列
- ~~SSE 流需要扩展以包含视频元数据~~ → 决定不扩展 SSE，用方案 C
- 文件上传类型的视频没有缩略图，需要处理降级展示（显示文件名+文件图标）

## Open Questions

(none — all resolved)

## Requirements (evolving)

- [R1] 处理等待页面展示视频缩略图（URL 类型）
- [R2] 处理等待页面展示视频标题（URL 类型）
- [R3] 处理等待页面展示平台标识（YouTube/Bilibili）
- [R4] 文件上传类型展示文件名（无缩略图时降级）
- [R5] 处理等待页面提供取消按钮
- [R6] 处理失败后提供重试按钮

## Acceptance Criteria (evolving)

- [ ] URL 类型任务处理时，等待页面显示封面、标题、平台标识
- [ ] 文件上传类型任务处理时，等待页面显示文件名
- [ ] 处理中可以取消任务，取消后有确认提示
- [ ] 处理失败后可以重试，重试有确认提示

## Definition of Done

- Tests added/updated (unit/integration where appropriate)
- Lint / typecheck / CI green
- Docs/notes updated if behavior changes
- Rollout/rollback considered if risky

## Out of Scope (explicit)

- 预估剩余时间 / 已等待时间计时器
- 队列系统（连续提交多个视频）
- 浏览器通知（处理完成推送）
- 封面虚化背景效果
- 取消时的后台资源清理（当前取消只标记状态，不中断进行中的 yt-dlp/LLM 调用）
- History 页面 StatusBadge 丰富化

## Technical Approach

### 后端改动

1. **DB**: tasks 表新增 `title TEXT` 列（migration via ALTER TABLE in `init_db`）
2. **`create_task()`**: 新增 `title` 参数
3. **`/process` 端点**: 在 `create_task()` 时传入 `video_info["title"]`；响应扩展含 title/thumbnail_url/platform
4. **`/upload` 端点**: 响应扩展含 file_name（title 为空）
5. **schemas.py**: `ProcessResponse`/`UploadResponse` 替代通用 dict 返回；确认 `TaskListItem` 含 title 字段

### 前端改动

1. **types/index.ts**: `ProcessResponse` 扩展字段（title, thumbnail_url, platform, file_name）
2. **api/client.ts**: `submitUrl` 返回类型更新；新增 `cancelTask()` / `retryTask()`
3. **NewNotePage.tsx**: 新增 `taskMeta` state；处理中渲染：视频信息卡片 → StepIndicator → 取消/重试按钮；文件上传降级显示文件名
4. **NoteDetailPage.tsx**: processing 状态同步展示视频信息卡片+按钮（元数据来自已有 fetchTaskById）
5. **新增组件**: `VideoInfoCard`（或内联，视复杂度）

### i18n

- 新增翻译 key: 取消确认/重试确认对话框文本

## Decision (ADR-lite)

**Context**: 前端需要在视频处理等待界面获取视频元数据（title, thumbnail_url, platform），当前 SSE 流不推送这些信息
**Decision**: 方案 C — 扩展 POST 响应 + 复用现有 fetchTaskById
- NewNotePage: `/process` 和 `/upload` 响应扩展返回 title/thumbnail_url/platform/file_name，前端直接从 POST 响应获取
- NoteDetailPage: 已有 `fetchTaskById()` 调用，`TaskListItem` schema 已含 thumbnail_url 和 title 字段，无需额外改动
**Consequences**: SSE 保持纯粹只推进度；零额外请求（NewNotePage）；后端需扩展两个 POST 端点的响应 schema

**布局**: 卡片在上 + 步骤在下 + 按钮在最下。视频信息卡片（封面+标题+平台标识）横排，下方 StepIndicator，最下方取消/重试按钮。层次清晰，改动小，窄屏自然适配。

### DB 变更

- tasks 表需新增 `title` 列
- `create_task()` 需接受 `title` 参数
- `/process` 端点在创建任务时需传入 `video_info["title"]`
