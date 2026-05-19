# Fix: page refresh loses auth state, user kicked to login

## Goal

修复页面刷新后用户被踢回登录页的问题。当前 access token 仅存于内存变量中，刷新后丢失，路由守卫立即 302 到登录页，而 refresh cookie 仍有效却未被主动使用。

## What I already know

- `token.ts` 中 access token 存在模块变量 `let accessToken: string | null = null`，刷新后归零
- `api.ts` 中 `refreshToken()` 可以用 httpOnly cookie 换取新 access token，但仅在 API 返回 401 时被动调用
- `main.tsx` 中 router 创建前没有 silent refresh 逻辑
- `authLoader` 在 `getAccessToken() === null` 时直接 302 到 `/auth/login`
- refresh token 存在 httpOnly cookie 中，path 为 `/api/auth/refresh`，max_age 7 天
- 后端 `/api/auth/refresh` 端点工作正常（token rotation 已实现）

## Requirements

- 应用启动时（router 创建前）主动调用 `/api/auth/refresh`，尝试用 refresh cookie 恢复 access token
- 若 refresh 成功，用户停留在当前页面；若失败，正常跳转登录页
- 刷新时应有短暂 loading 状态，避免闪屏（先显示空白/loading → 拿到 token → 正常渲染；或跳转登录页）

## Acceptance Criteria

- [ ] 已登录用户刷新页面后仍停留在原页面，不跳转登录页
- [ ] 未登录用户刷新后正常跳转登录页
- [ ] refresh cookie 过期/无效时正确跳转登录页
- [ ] 刷新过程中无白屏闪烁或短暂闪现登录页再跳回

## Definition of Done

- Lint / typecheck 通过
- 手动验证上述 acceptance criteria
- 无新增安全漏洞（不将 access token 存入 localStorage）

## Out of Scope

- 不改变 token 存储策略（不引入 localStorage/sessionStorage 存 access token）
- 不重构现有 auth 架构（保持 httpOnly cookie + 内存 access token 的双 token 设计）
- 不新增"记住我"功能

## Decision (ADR-lite)

**Context**: 页面刷新后 access token 丢失，需要在应用启动时恢复登录状态。
**Decision**: 在 `main.tsx` 中 router 创建前 await silent refresh（方案 1）。
**Consequences**: 实现最简，延迟 <100ms 几乎无感；需注意 StrictMode 双渲染不会触发重复 refresh（refresh 只在模块初始化时执行一次，不受 React 渲染影响）。

## Technical Notes

- 关键文件：`frontend/src/main.tsx`（router 创建前加 silent refresh）、`frontend/src/auth/api.ts`（导出 silentRefresh 供启动调用）
- React Router v7 Data mode：在 router 创建前做 async init
- StrictMode 双渲染不影响（refresh 在 React 外执行，只跑一次）
