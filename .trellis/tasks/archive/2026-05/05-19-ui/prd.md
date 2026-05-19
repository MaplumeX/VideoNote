# 优化历史界面 UI 布局

## Goal

重构历史页面（HistoryPage），提升信息密度、交互效率与视觉层次，使其从"工具感"升级为"软件感"。

## Requirements

### 1. 视图模式：卡片默认 + 列表可切换
- 卡片视图保持当前双列网格为默认
- 新增列表视图（紧凑行，类似文件管理器：标题/来源/日期/状态/标签一行显示）
- 顶栏提供视图切换图标按钮
- 视图偏好可存入 localStorage

### 2. 筛选布局：顶栏筛选条 + Sheet 侧栏
- 顶栏：搜索框 + 当前激活的筛选 pills（文件夹/标签/收藏），可点击 × 移除
- Sheet 侧栏：保留 ContentSidebar 完整功能（文件夹/标签 CRUD + 筛选），通过按钮从左侧滑出，不常驻
- ContentSidebar 组件复用，改为在 Sheet/Drawer 中渲染

### 3. 后端关键词搜索
- 后端 db.py 的 fetchTasks 增加 `search` 参数，SQL LIKE 匹配 title
- routes.py /api/tasks 接收 search query param
- 前端 fetchTasks 传递 search 参数，搜索框 debounce 300ms

### 4. 排序支持
- 列表视图支持按日期/标题排序
- 后端 fetchTasks 增加 `sort_by` + `sort_order` 参数
- 顶栏排序下拉选择器

### 5. 批量操作 action bar
- 选中项目后，页面底部/顶部出现固定 action bar（类似 Gmail）
- 包含：批量打标签、批量移动、批量收藏/取消收藏、批量删除
- 显示已选数量 + 全选/取消全选

### 6. 卡片操作改进：收藏常驻 + 右键菜单
- 收藏星标常驻显示（不再 hover 才出现）
- 其他操作（删除、重试、取消、选择）放入右键上下文菜单
- 保留 hover 时的删除快捷入口（可选）

### 7. 分页组件升级
- 使用 shadcn/ui Pagination 组件
- 显示页码按钮（1 2 3 ... 10），支持跳转
- 显示总数信息

## Acceptance Criteria

- [ ] 用户可在卡片视图和列表视图间切换，偏好持久化
- [ ] 列表视图支持按日期/标题排序
- [ ] 顶栏搜索框输入关键词可过滤结果（后端 API）
- [ ] 激活的筛选条件以 pills 显示在顶栏，可 × 移除
- [ ] 侧栏改为 Sheet 滑出，不常驻占位
- [ ] 选中项目后出现 action bar，含完整批量操作
- [ ] 收藏星标常驻可见
- [ ] 右键菜单包含删除/重试/取消/选择操作
- [ ] 分页显示页码，支持跳转
- [ ] 暗色/亮色模式兼容
- [ ] 响应式布局正常
- [ ] i18n key 补全
- [ ] Lint / typecheck 通过

## Definition of Done

- Lint / typecheck 通过
- 暗色/亮色模式兼容
- 响应式布局正常
- i18n key 补全
- 后端新增 search/sort 参数有对应测试

## Out of Scope

- 视频缩略图预览（后端无 thumbnail 字段）
- 视频时长显示（后端无 duration 字段）
- 笔记摘要预览（result_json 列表 API 不返回）
- 无限滚动分页
- 触屏 long-press 右键菜单 fallback
- 导出/分享等未来右键菜单项

## Decision (ADR-lite)

**Context**: 历史页面信息密度低、交互隐蔽、缺少搜索排序
**Decision**:
- 视图：卡片默认 + 列表切换
- 筛选：顶栏筛选条（搜索+ pills）+ Sheet 侧栏（完整 CRUD）
- 搜索：后端 API LIKE 搜索
- 排序：后端 sort_by/sort_order 参数，列表视图支持
- 批量操作：选中后浮动 action bar
- 卡片操作：收藏常驻 + 右键菜单
- 分页：页码组件
**Consequences**: 需前后端同步改动；右键菜单在触屏需后续适配；卡片信息受限于后端现有字段

## Technical Notes

### 前端
- 文件：HistoryPage.tsx, ContentSidebar.tsx, StatusBadge.tsx
- 新增：ContextMenu 组件、Actionbar 组件、Pagination 组件
- API：fetchTasks 增加 search/sort_by/sort_order 参数
- 路由：/app/history
- URL params：增加 search, sort_by, sort_order, view

### 后端
- db.py：fetchTasks 增加 search（LIKE title）、sort_by/sort_order 参数
- routes.py：/api/tasks 接收 search, sort_by, sort_order query params
- TaskItem 类型不需要改（title 已有）
