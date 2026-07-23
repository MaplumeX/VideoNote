# 核心链路七项缺陷实施计划

## Phase A：测试基础与持久化契约

- [x] 修正后端开发依赖安装方式，使 pytest、pytest-asyncio、Ruff 在标准开发环境可用。
- [x] 为前端增加最小 Vitest/jsdom 测试配置和脚本，不改变生产构建。
- [x] 给 `tasks` 增加恢复/取消字段及兼容迁移。
- [x] 增加非终态任务查询、原子取消、恢复尝试和终态输入清理所需数据库函数。
- [x] 增加迁移与数据库状态机回归测试。

验证：

```bash
cd backend && uv run --extra dev pytest
cd backend && uv run --extra dev ruff check app tests
cd frontend && npm test -- --run
```

## Phase B：任务运行器、重启恢复和取消

- [x] 新增单进程任务运行器，持有强引用、防止重复调度并支持用户取消/应用关闭。
- [x] URL、上传、重试入口统一通过运行器调度。
- [x] 上传任务持久化安全源文件路径，调整清理时机。
- [x] lifespan 启动时恢复有效非终态任务；无效输入进入明确失败态。
- [x] 处理管线在耗时阶段前后检查取消；CancelledError 与普通失败分流。
- [x] 删除和批量删除运行中任务前先持久化取消并通知运行器。
- [x] 增加 URL/上传重启恢复、重复调度、取消后不进入后续阶段的测试。

回滚点：完成数据库迁移后先验证旧终态任务可读取；运行器接管入口前保留小步提交边界。

## Phase C：前端传输与鉴权可靠性

- [x] 后端将上传语言声明为 multipart Form 字段，补充接口测试。
- [x] 前端上传保留 XHR 进度，验证语言字段，并为 401 提供明确可恢复错误。
- [x] 用共享 refresh Promise 重构 `authFetch`，增加一次重试上限和统一失败传播。
- [x] 抽出可单测 SSE 增量解析器，修复跨 chunk 状态。
- [x] `useSSE` 增加任务状态兜底、有限退避重连和完整清理。
- [x] 增加上传、鉴权并发和 SSE 任意分包测试。

## Phase D：编辑数据一致性

- [x] 把自动保存改为不可变快照、单请求串行和保存追赶机制。
- [x] 保持 1.5 秒防抖、Cmd/Ctrl+S 与编辑器不重建约束。
- [x] 保存失败保持 dirty；新编辑或手动保存可以重试。
- [x] 增加首次单字符、保存中继续编辑、失败重试和响应顺序测试。

回滚点：不得恢复“保存响应覆盖编辑器 Markdown”的旧行为。

## Phase E：标签权限

- [x] 把已有标签归属校验与关联写入下沉为用户作用域事务。
- [x] 路由传入 `user_id`，非法或跨用户标签返回结构化 404。
- [x] 启动迁移清理历史跨用户关联。
- [x] 增加同用户、跨用户、混合原子失败和清理测试。

## Phase F：全量验证与文档

- [x] 运行全部后端测试和 Ruff。
- [x] 运行前端测试、lint 和生产构建。
- [x] 检查 OpenAPI：上传语言属于 multipart body。
- [x] 检查数据库旧数据兼容和恢复路径安全。
- [x] 检查中英文结构化错误翻译完整。
- [x] 检查 Docker 单镜像配置、lifespan 启停与重启恢复契约；真实容器重启作为部署验收项。
- [x] 更新相关 Trellis backend/frontend 规范，记录持久任务、SSE 分包、保存快照和用户作用域写入约束。

最终验证：

```bash
cd backend && uv run --extra dev pytest
cd backend && uv run --extra dev ruff check app tests
cd frontend && npm test -- --run
cd frontend && npm run lint
cd frontend && npm run build
git diff --check
git status --short
```

## Risk Files

- `backend/app/db.py`：兼容迁移和终态守卫。
- `backend/app/main.py`：lifespan 恢复与关闭顺序。
- `backend/app/api/routes.py`：处理管线、上传、取消和恢复输入。
- 新任务运行器模块：强引用、重复调度和关闭语义。
- `frontend/src/auth/api.ts`：所有 API 的鉴权重试。
- `frontend/src/hooks/useSSE.ts`：长连接和重连清理。
- `frontend/src/pages/NoteDetailPage.tsx`：编辑数据一致性。

## Review Gates

- [x] 规划审批后才运行 `task.py start`。
- [x] Phase A/B 完成后先审查任务状态机，再继续前端改动。
- [x] Phase C/D 完成后运行前端专项测试，确认没有隐藏 pending Promise。
- [x] Phase E 完成后运行双用户权限测试。
- [x] 最终检查不得依赖真实第三方 API。

## Validation Record

- `backend`: 17 tests passed；Ruff passed。
- `frontend`: 23 tests passed；ESLint passed；production build passed。
- 两轮独立质量审查完成，第二轮无 blocker/high 问题。
- 已知部署验收项：真实 Docker 进程重启演练未在当前环境执行；单镜像配置、lifespan 恢复路径与关闭语义已通过代码和自动化测试检查。
