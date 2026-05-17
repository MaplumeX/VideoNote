# 用户系统

## Goal

为 VideoNote 添加用户系统，实现用户注册/登录、JWT 身份认证、资源隔离和任务历史页面。

## Requirements

* 资源隔离：每个用户只能访问自己的笔记/任务，防止他人通过 job_id 越权访问
* 访问控制：未登录用户不能使用服务，全部 API 需认证
* 任务历史列表页：用户可查看自己的历史任务记录
* 认证方式：JWT + Refresh Token（access 15min / refresh 7d）
* 登录方式：仅邮箱/密码注册登录，无第三方 OAuth
* 前端路由：React Router v7 Data mode（createBrowserRouter）
* Token 存储：Access Token 存内存（JS 模块变量），Refresh Token 用 HttpOnly Cookie
* CORS 收紧：从 `allow_origins=["*"]` 改为指定前端 URL

## Acceptance Criteria

* [ ] 用户可注册（邮箱+密码）并登录
* [ ] 登录后返回 access token（JSON）+ refresh token（HttpOnly Cookie）
* [ ] Access token 过期后，前端自动 refresh 无感刷新
* [ ] Refresh token 轮换：每次刷新撤销旧 token、签发新 token
* [ ] Refresh token 重用检测：发现重用则撤销该用户所有 token
* [ ] 未登录访问任何 API 返回 401
* [ ] 用户只能访问自己的任务（按 user_id 过滤）
* [ ] 任务历史页面：列出当前用户所有任务，可查看结果
* [ ] 登录/注册页面正确展示，已登录用户访问登录页自动跳转
* [ ] 未登录用户访问受保护页面自动重定向到登录页（保留目标 URL）
* [ ] 登出功能：撤销 refresh token + 清除 cookie
* [ ] CORS 仅允许配置的前端源

## Definition of Done

* Tests added/updated（后端 auth 接口 + 前端组件）
* Lint / typecheck green
* bcrypt 同步调用用 `asyncio.to_thread()` 包装
* CORS 配置可环境变量控制

## Technical Approach

### 后端

* **依赖**: PyJWT + bcrypt（不用 python-jose / passlib）
* **数据库**: 新增 `users` 表 + `refresh_tokens` 表（遵循现有 aiosqlite + raw SQL 模式）
* **Auth 路由**: `/api/auth/register`、`/api/auth/login`、`/api/auth/refresh`、`/api/auth/logout`
* **保护机制**: `Depends(get_current_user)` + `HTTPBearer` 依赖注入
* **Refresh token**: 不存原文，存 SHA-256 hash；单次使用+轮换；条件 UPDATE 防竞态
* **tasks 表**: 新增 `user_id` 列，所有查询按 user_id 过滤
* **bcrypt**: 用 `asyncio.to_thread()` 包装避免阻塞事件循环
* **Cookie**: `path="/api/auth/refresh"` 限定范围，`httponly=True, secure=True, samesite="lax"`
* **CORS**: `allow_origins=[FRONTEND_URL]`，`allow_credentials=True`
* **清理**: 启动时清理过期 30 天的 refresh token

### 前端

* **路由**: React Router v7 Data mode（`createBrowserRouter` + `RouterProvider`）
* **路由结构**: 公开路由（`/auth/login`、`/auth/register`）+ 受保护路由（`/app/*`）用 Layout route guard
* **Token 管理**: `src/auth/token.ts` 模块级变量存 access token；refresh token 由浏览器 cookie 自动携带
* **API 层**: 扩展 `client.ts`，注入 `Authorization: Bearer` header，拦截 401 自动 refresh，并发请求排队
* **页面**: LoginPage、RegisterPage、HistoryPage（新增）；VideoInput/Processing/Result 迁移到 `/app` 下

### 数据库 Schema

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

-- tasks 表新增 user_id 列
ALTER TABLE tasks ADD COLUMN user_id TEXT REFERENCES users(id);
```

## Decision (ADR-lite)

**Context**: 需要选择认证方案和前端路由方案
**Decision**: JWT + Refresh Token（PyJWT + bcrypt）；React Router v7 Data mode；HttpOnly Cookie 存储 refresh token
**Consequences**: 无状态认证适合 SQLite 架构；Data mode 提供路由级 auth guard；HttpOnly Cookie 防 XSS 但需 CORS 收紧；bcrypt 同步调用需 to_thread 包装

## Out of Scope

* 密码重置/忘记密码流程
* 邮箱验证
* 第三方 OAuth 登录
* 用户管理后台（封禁等）
* 付费/配额系统（仅预留 user_id 扩展点）
* 删除账号功能

## Research References

* [`research/jwt-refresh-fastapi.md`](research/jwt-refresh-fastapi.md) — PyJWT + bcrypt + refresh token 轮换 + SQLite 竞态处理
* [`research/react-router-v7-auth.md`](research/react-router-v7-auth.md) — Data mode 路由 + Layout route guard + token refresh 拦截

## Technical Notes

* 当前 `allow_origins=["*"]` + `allow_credentials=True` 在浏览器端会导致 cookie 被静默丢弃——必须收紧 origin
* bcrypt `rounds=12`（~250ms），必须用 `asyncio.to_thread()` 包装
* Refresh token cookie `path="/api/auth/refresh"` 减少传输范围
* tasks 表新增 user_id 需要迁移现有数据（可设为 NULL 或创建匿名用户）
* SECRET_KEY 需加入 .env 配置，开发环境可自动生成
