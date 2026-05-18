# Enhance Task Features

## Goal

为 VideoNote 的任务系统增加 5 项核心能力：删除、重试、取消、分页、元数据，使历史页面可用且可管理。

## What I already know

* 任务模型：`jobs` 表，字段 `job_id, user_id, stage, progress, message, result_json, created_at, updated_at`
* 任务阶段：`pending → downloading → extracting_subtitles → transcribing → generating_notes → complete/failed`
* 前端流程：`input → processing → result`，SSE 实时推送进度
* 历史页面：`HistoryPage` 列出所有任务，无分页，无删除，无重试
* 无取消机制：`asyncio.create_task` 启动后无法从 API 中止
* 无元数据：不存储视频 URL、文件名、平台、语言等信息
* 认证：所有端点需 JWT，任务按 user_id 隔离

## Technical Approach

### DB 变更
* `jobs` 表新增列：`video_url TEXT`, `file_name TEXT`, `platform TEXT`, `language TEXT`, `source_type TEXT`（"url" / "upload"）
* `TaskStage` 枚举新增 `cancelled`
* `create_task()` 签名扩展，接受元数据参数
* 新增 `delete_task(job_id)`, `count_user_tasks(user_id)` 函数
* `get_user_tasks()` 增加 `limit` / `offset` 参数

### API 变更
* `POST /api/process` — 创建任务时写入元数据（video_url, platform, language, source_type="url"）
* `POST /api/upload` — 创建任务时写入元数据（file_name, language, source_type="upload"）
* `GET /api/tasks` — 增加 `page` / `limit` 查询参数，返回 `{items, total, page, limit}`
* `DELETE /api/tasks/{job_id}` — 硬删除任务记录
* `POST /api/tasks/{job_id}/retry` — 仅 source_type="url" 且 stage="failed" 时允许，用元数据中的 video_url + language 创建新任务
* `POST /api/tasks/{job_id}/cancel` — 将进行中任务 stage 改为 cancelled，SSE 循环检测到后推送并关闭

### 前端变更
* `HistoryPage` — 显示元数据（URL/文件名、平台、语言），分页控件，删除/重试/取消按钮
* `types/index.ts` — 更新 TaskItem, TaskStage, 新增分页响应类型
* `useSSE` — 处理 cancelled 状态

## Requirements

* [R1] 任务删除：用户可删除历史任务（硬删除，直接从 DB 移除）
* [R2] 失败重试：failed 任务可重新执行（复用元数据中的 video_url，仅 URL 类型任务可重试；文件上传类型因原文件已清理不可重试）
* [R3] 任务取消：进行中任务可被中止（标记取消方案 — API 标记 cancelled，SSE 检测后关闭连接，后台任务仍跑完但结果丢弃）
* [R4] 历史分页：任务列表支持分页（offset 分页 `?page=1&limit=20`，返回 total 数量）
* [R5] 任务元数据：存储视频来源信息（URL/文件名/平台/语言）

## Acceptance Criteria

* [ ] DELETE /api/tasks/{job_id} 删除任务，历史列表不再显示
* [ ] POST /api/tasks/{job_id}/retry 对 failed+URL 类型任务重新执行，返回新 job_id
* [ ] POST /api/tasks/{job_id}/cancel 标记进行中任务为 cancelled，SSE 推送后关闭
* [ ] GET /api/tasks?page=1&limit=20 返回分页结果含 total
* [ ] 历史页显示 video_url / file_name / platform / language
* [ ] 文件上传类型 failed 任务的重试按钮禁用或不显示

## Definition of Done

* 后端 API + 前端 UI 均实现
* 类型检查通过
* 关键路径有测试

## Out of Scope (explicit)

* 任务编辑（修改标题等）
* 批量操作（批量删除/重试）
* 任务搜索/筛选
* 软删除/回收站恢复
* 取消竞态保护（取消与完成竞争时取实际状态）
* 元数据字段预留扩展（video_duration 等）

## Technical Notes

* 后端入口：`backend/app/routes.py` — 所有任务 API
* 数据库层：`backend/app/db.py` — `jobs` 表定义 + CRUD
* Schema：`backend/app/schemas.py` — Pydantic 模型
* 前端历史页：`frontend/src/pages/HistoryPage.tsx`
* 前端类型：`frontend/src/types/index.ts`
* SSE Hook：`frontend/src/hooks/useSSE.ts`
* 处理流水线：`backend/app/routes.py` 中 `_process_video_url` / `_process_video_file`
