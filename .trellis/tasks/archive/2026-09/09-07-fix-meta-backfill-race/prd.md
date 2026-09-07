# Fix task meta backfill race in NewNotePage execution view

## Problem

提交新任务（URL）后跳转到的执行详情界面（`NewNotePage` 的 processing 分支）在整个任务运行期间不显示视频标题和封面。

## Root cause

前后端时序竞态：

- 后端 orchestrator 在任务调度后立即写入 `status=running, phase=fetching` 并通过 SSE 推送；`update_task_meta`（写入 title/thumbnail）要等 fetching 阶段（yt-dlp dump-json + 封面下载）完成后才执行。
- `NewNotePage` 的一次性回填 effect（`metaFetchedFor` ref 守卫）在 SSE 状态首次变为非 `pending` 时 `fetchTaskById` —— 此刻 fetch 阶段刚开始，拉到的 title/thumbnail 仍为 NULL。
- 之后 `update_task_meta` 落库，但前端不再重新拉取 → `VideoInfoCard` 整个执行期间无标题/封面。

代码注释中的假设（"populated ... before the first non-pending progress"）与实际顺序相反。

## Requirements

1. `NewNotePage` 在任务的 `video_meta` 落库后（即 fetching 阶段推进到后续阶段时）重新拉取 task meta，回填 `taskMeta.title` / `taskMeta.thumbnail_url`。
2. 不破坏现有行为：
   - 重试（retry）后 `metaFetchedFor` 重置、重新回填；
   - 上传任务（无 title/thumbnail）不回归；
   - `NewNotePage` 完成后导航到 `NoteDetailPage` 的既有流程不变。

## Acceptance criteria

- 提交一个 URL 任务后停留在 NewNotePage 执行界面，fetching 阶段完成、进入下一阶段时，`VideoInfoCard` 显示标题和封面。
- 无回归：既有 `NewNotePage.test` / 相关测试全部通过；新增针对回填时机的测试覆盖（phase 推进触发 refetch）。
- 不修改后端。

## Scope

- 只改 `frontend/src/pages/NewNotePage.tsx`（及对应测试）。
- 轻量级任务：PRD-only。
