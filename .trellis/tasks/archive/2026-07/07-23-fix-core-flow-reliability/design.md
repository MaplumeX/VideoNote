# 核心链路七项缺陷修复设计

## 1. Architecture Boundaries

保持现有 React SPA、FastAPI、SQLite 和单镜像部署，不引入 Redis、ARQ 或独立 Worker。

本次新增或收敛三个内部边界：

1. **前端可靠客户端边界**
   - `auth/api.ts`：所有普通 API 的单飞刷新与一次重试。
   - `useVideoUpload.ts`：XHR 上传、multipart 语言字段、鉴权失败的明确结果。
   - `useSSE.ts`：标准 SSE 增量解析、有限重连和任务状态兜底。
   - `NoteDetailPage.tsx`：快照化、串行、可追赶的自动保存状态机。

2. **后端持久任务边界**
   - 新增轻量任务运行器模块，持有 `job_id -> asyncio.Task` 强引用。
   - SQLite `tasks` 表持久化恢复所需输入、取消意图和执行尝试信息。
   - API 创建任务后交给运行器调度；应用启动时运行器扫描并恢复非终态任务。

3. **用户作用域数据边界**
   - 标签关联写入必须显式携带 `user_id`。
   - 路由校验与数据库条件共同保证笔记、标签、用户三者一致。

## 2. Data Model

在现有 `tasks` 表通过兼容式迁移增加：

| Column | Type | Purpose |
|---|---|---|
| `input_file_path` | TEXT nullable | 上传任务恢复时定位持久卷中的源文件 |
| `cancel_requested` | INTEGER NOT NULL DEFAULT 0 | 持久化取消意图 |
| `attempt_count` | INTEGER NOT NULL DEFAULT 0 | 记录启动/恢复尝试次数 |

现有 `video_url`、`language`、`source_type` 已足够恢复 URL 任务。

不新增通用分布式租约字段：Dockerfile 明确使用单个 Uvicorn 进程，本任务也不支持多实例调度。运行器注册表负责当前进程内防重；启动恢复仅在 lifespan 初始化期间执行一次。

`note_tags` 暂不做破坏性表重建。通过事务化的用户作用域查询写入，并在迁移阶段删除 `tasks.user_id != tags.user_id` 的历史关联，满足当前正确性。复合外键可在未来正式迁移系统中补充。

## 3. Task Lifecycle

### 3.1 Creation

```text
API validates input
  → persist task + recoverable input
  → task runner schedule(job_id)
  → response returns existing API schema
```

上传文件写入 `UPLOAD_DIR` 后，将完整服务端路径存入 `input_file_path`。文件只在任务到达 `complete`、`failed` 或用户请求的 `cancelled` 后清理。

### 3.2 Startup Recovery

应用启动：

1. `init_db()` 完成迁移。
2. 查询所有非终态任务。
3. 校验恢复输入：
   - URL 任务必须有受支持的 `video_url`。
   - 上传任务必须有存在且位于 `UPLOAD_DIR` 内的 `input_file_path`。
4. 输入有效则重新调度并递增 `attempt_count`。
5. 输入缺失或不安全则写入结构化可重试失败消息，不能继续保持处理中。

恢复从任务开头重新执行，不尝试从 ASR/LLM 中间步骤续跑。最终写入继续由终态守卫保护，保证重复尝试不会覆盖取消状态。

### 3.3 Cancellation

取消顺序：

1. 原子设置 `cancel_requested = 1` 和 `stage = cancelled`。
2. 通知运行器取消对应 `asyncio.Task`。
3. 每个耗时阶段前后检查取消状态。
4. `CancelledError` 不进入普通失败处理；始终执行资源清理。
5. 已进入不可撤回的同步线程/第三方调用可以自然返回，但返回后必须在下一检查点终止，不能进入下一阶段或保存结果。

运行器关闭应用时取消内存任务，但不设置用户取消意图；上传源文件保留，让下一次启动恢复。用户取消则清理上传源文件。

## 4. Frontend State Machines

### 4.1 Auto-save

维护：

- `editMarkdownRef`：最新编辑内容。
- `lastSavedMarkdownRef`：服务器确认保存的确切快照。
- `saveInFlightRef`：当前保存 Promise。
- `saveQueuedRef`：请求期间是否又有新内容。
- 防抖 timer。

保存算法：

1. 调用时读取并冻结 `snapshot`。
2. 若已有请求执行，仅标记 queued。
3. 请求成功后只把 `snapshot` 写入 `lastSavedMarkdownRef`。
4. 请求结束后比较最新内容；不同则立即保存最新快照。
5. 保存失败保留 dirty，后续编辑或手动保存可重试。

不把后端返回 Markdown反向覆盖编辑器，从而保持 Milkdown 焦点和编辑历史。

### 4.2 Auth Refresh

用模块级 `refreshPromise` 替代 callback 队列：

```text
first 401 → create refreshPromise
other 401 → await same promise
success → each original request retries once
failure → every waiter rejects; clear auth; single redirect path
finally → clear refreshPromise
```

内部请求选项增加不可透传给 `fetch` 的 retry 标记，保证最多一次。

XHR 上传不自动静默重传大文件。上传前确保存在 access token；若服务器返回 401，尝试刷新登录状态并返回“登录已恢复，请重新上传”的结构化前端错误，避免无提示卡住或重复消耗带宽。

### 4.3 SSE Parser and Recovery

解析器作为可单测的纯函数/小模块，状态跨 chunk 保留：

- 支持 `\r\n`、`\n`、EOF flush。
- 收集多个 `data:` 行并用换行拼接。
- 空行完成一次事件派发。
- 忽略注释和未知字段。

连接中断：

1. 获取任务详情。
2. `complete`：获取结果并结束。
3. `failed/cancelled`：设置对应终态并结束。
4. 非终态：最多有限次数指数退避重连。
5. job 切换或组件卸载：AbortController 取消连接和等待。

## 5. API Contracts

- `/api/upload` 路径不变，`language` 从 query 更正为 multipart form 字段。
- 现有任务、进度、结果、取消 API 路径和响应主体保持兼容。
- 新增内部数据库字段不暴露给现有前端类型，除非任务恢复 UI 明确需要。
- 新错误使用 `error_detail()` 结构化错误码，并补齐 `en`、`zh-CN`。
- 越权标签继续返回 404，避免泄露标签存在性。

## 6. Transactions and Security

标签批量校验和写入必须在同一数据库连接/事务中完成：

1. 验证任务属于 `user_id`。
2. 一次查询确认所有去重后的 `tag_ids` 都属于 `user_id`。
3. 数量不匹配时回滚并返回失败。
4. 全部合法后写入关联并提交。

启动迁移清理历史跨用户关联：

```sql
DELETE FROM note_tags
WHERE EXISTS (
  SELECT 1
  FROM tasks n
  JOIN tags t ON t.id = note_tags.tag_id
  WHERE n.job_id = note_tags.job_id
    AND n.user_id != t.user_id
);
```

恢复上传路径必须 `resolve()` 后确认位于 `UPLOAD_DIR` 内，不能信任数据库中的原始路径字符串。

## 7. Compatibility and Rollback

- 所有迁移使用项目既有的 `ALTER TABLE ...` + `OperationalError` 兼容模式。
- 旧数据库没有新字段时自动补齐；旧终态任务不受影响。
- 旧的非终态上传任务没有 `input_file_path`，启动时会进入明确失败态，而非无限挂起。
- 回滚旧版本时新增列会被忽略，不影响旧查询。
- 若任务运行器出现问题，可回滚调度调用并保留数据库迁移；新增列不会破坏旧版本。

## 8. Testing Strategy

### Backend

- 数据库迁移、启动恢复、输入缺失、重复调度。
- URL/上传任务在各阶段取消，确认后续服务未调用、结果未写入。
- 上传 multipart 语言。
- 标签同用户、跨用户、混合标签原子失败、历史脏关联清理。
- 外部服务全部 mock，不产生真实 API 请求。

### Frontend

- 自动保存首次编辑、请求中继续编辑、失败重试和手动保存。
- SSE 在任意 chunk 边界、CRLF/LF、多 data 行、断线后的终态/重连。
- 多个 401 共享一次 refresh；成功统一重试；失败全部 reject；不无限循环。
- XHR 上传语言字段和 401 用户反馈。

## 9. Risks

- `asyncio.to_thread()` 无法强制杀死已经运行的 Python 线程；设计通过任务取消和阶段检查保证不再继续消费后续 ASR/LLM 阶段。对 yt-dlp/ffmpeg 的进一步硬终止只在现有服务封装可安全支持时实施。
- SQLite 单进程运行器不支持多个应用实例同时领取任务；部署文档继续明确单实例约束。
- 前端当前没有 Vitest 配置，需要新增最小测试基础设施和开发依赖。
