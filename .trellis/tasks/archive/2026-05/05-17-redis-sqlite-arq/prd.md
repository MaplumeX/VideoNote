# 移除 Redis 依赖，用 SQLite + 进程内任务替代 ARQ

## Goal

移除 Redis 和 ARQ 依赖，将任务队列改为进程内 asyncio 执行，将任务状态存储从 Redis Hash 迁移到 SQLite。降低 MVP 部署复杂度，消除对外部服务的依赖。

## Requirements

* 移除 `arq` 和 `redis` 依赖
* 移除 `REDIS_URL` 配置
* 删除 `worker.py` 独立进程
* 任务在 FastAPI 进程内通过 asyncio.create_task 执行
* 任务进度和结果存储到 SQLite
* SSE 端点改从 SQLite 读取进度
* 结果端点改从 SQLite 读取结果
* 保留现有 API 接口不变（/process, /upload, /tasks/{job_id}/progress, /tasks/{job_id}/result）

## Acceptance Criteria

- [ ] `pip install` 不再包含 arq 和 redis
- [ ] 无 Redis 相关代码残留（config, routes, worker 全部清理）
- [ ] /process 和 /upload 端点正常返回 job_id
- [ ] SSE 进度推送正常工作
- [ ] /tasks/{job_id}/result 端点正常工作
- [ ] Lint / typecheck green

## Definition of Done

* Lint / typecheck green
* 不再需要 Redis 即可运行
* .env.example 移除 REDIS_URL

## Technical Approach

1. **新增 `app/db.py`**：SQLite 数据库管理，创建 tasks 表（job_id, stage, progress, message, result_json, created_at, updated_at），使用 aiosqlite 异步操作
2. **改造 `routes.py`**：移除 ARQ/Redis 导入和调用；/process 和 /upload 用 `asyncio.create_task` 启动处理函数；进度/结果读写改调 db.py
3. **迁移 `worker.py` 核心逻辑**：将 `process_video_url` 和 `process_video_file` 移为进程内 async 函数，进度/结果写入 SQLite
4. **删除 `worker.py`**
5. **清理 `config.py`**：移除 REDIS_URL
6. **清理 `pyproject.toml`**：移除 arq、redis 依赖
7. **清理 `.env.example`**：移除 REDIS_URL

### SQLite 表设计

```sql
CREATE TABLE IF NOT EXISTS tasks (
    job_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL DEFAULT 'pending',
    progress REAL NOT NULL DEFAULT 0.0,
    message TEXT NOT NULL DEFAULT '',
    result_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### SSE 轮询

保持 1s 间隔轮询 SQLite，WAL 模式下并发读无压力。

## Out of Scope

* 多 worker 横向扩展
* 任务优先级调度
* 任务重试机制
* 重启时恢复/标记进行中任务
* 过期清理（Redis expire 替代方案）

## Technical Notes

* 涉及文件：worker.py（删除）, routes.py（改造）, config.py（清理）, pyproject.toml（清理）, .env.example（清理）
* 新增文件：app/db.py（SQLite 管理）
* 依赖变更：移除 arq>=0.26.0、redis>=5.0.0；新增 aiosqlite
* worker.py 中 process_video_url / process_video_file 的核心处理逻辑不变，只改进度/结果写入方式
* routes.py 中 SSE event_generator 改为从 SQLite 读取
