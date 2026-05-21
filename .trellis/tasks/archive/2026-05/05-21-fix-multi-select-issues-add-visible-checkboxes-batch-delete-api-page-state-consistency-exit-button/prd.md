# Fix Multi-Select Issues in HistoryPage

## Goal

修复笔记历史页面的多选功能，使其完整可用：添加可见复选框、实现后端批量删除 API、修复翻页/筛选时的选中状态一致性、添加退出多选模式的明确交互。

## What I already know

* 多选目前只能通过右键菜单触发（HistoryPage.tsx:447-449），卡片/列表上无可见 checkbox
* 批量删除用 Promise.all 发送 N 个独立 DELETE 请求（HistoryPage.tsx:371-387），后端无 batch/delete 端点
* 单条删除端点在 routes.py:466，会同时 cancel 进行中的任务
* 切换筛选会清空 selectedIds（HistoryPage.tsx:218），但翻页不会，导致选中项可能不可见
* 批量操作栏只有"取消全选"按钮，无 Escape 键或关闭按钮退出多选
* 后端已有 batch/untag 端点但前端未暴露
* 批量操作模式：batch_add_tag 逐条 INSERT，其他用 SQL IN 子句

## Assumptions (temporary)

* checkbox 交互应遵循常见 UX 模式（点击 checkbox 进入多选模式，不影响卡片点击导航）
* 后端 batch delete 应复用现有 delete_task 逻辑（含 cancel 逻辑）
* 翻页时应清空选中状态，保持一致性

## Decisions

* D1: Checkbox 放在左上角常驻显示，选中时有高亮边框（类似 Google Photos）
* D2: 批量删除确认对话框中显示待删数量

## Requirements

* R1: 卡片视图和列表视图左上角添加常驻可见 checkbox，点击切换选中
* R2: 后端新增 POST /tasks/batch/delete 端点，前端调用替代 N 个独立 DELETE；确认对话框显示待删数量
* R3: 翻页时清空 selectedIds，保持选中状态与可见项一致
* R4: Escape 键清空选中 + 批量操作栏添加 X 关闭按钮

## Acceptance Criteria

* [ ] 卡片/列表左上角常驻 checkbox，点击切换选中
* [ ] 点击 checkbox 不触发卡片导航（stopPropagation）
* [ ] 批量删除使用单一 POST /tasks/batch/delete API
* [ ] 删除确认弹窗显示待删笔记数量
* [ ] 翻页后选中状态清空
* [ ] Escape 键清空选中、退出多选模式
* [ ] 批量操作栏有 X 关闭按钮
* [ ] 已有批量操作（tag/move/favorite）不受影响

## Definition of Done

* Lint / typecheck 通过
* 手动验证多选流程完整可用
* 后端 API 遵循现有 batch 端点模式

## Out of Scope

* 键盘范围选择（Shift+Click）
* Cmd+A 全选快捷键
* 前端暴露 batch untag（独立需求）

## Technical Notes

* 后端 batch 端点模式：在 note_routes.py 中定义，使用 schemas.py 的 request model，调用 db.py 的 batch_* 函数
* 单条 delete 逻辑在 routes.py:466，含 cancel 逻辑 — batch_delete 需复用此逻辑
* db.py delete_task 支持 user_id 过滤（343-356 行）
* 前端 api/client.ts 已有 batchAddTag/batchMoveToFolder/batchSetFavorite 的模式
