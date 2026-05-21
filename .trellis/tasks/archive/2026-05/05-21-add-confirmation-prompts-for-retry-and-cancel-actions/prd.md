# Add confirmation prompts for retry and cancel actions

## Goal

为 HistoryPage 中的重试和取消操作添加确认提示，防止误操作。

## What I already know

* 项目已有 `window.confirm()` 模式：`handleDelete` (line 315) 使用 `t("history.deleteConfirm")`
* `handleRetry` (line 326) 和 `handleCancel` (line 338) 无任何确认直接执行
* 这两个操作可通过卡片内联按钮和右键上下文菜单触发
* i18n 文件已有 `history.retry`、`history.cancel`、`history.retryFailed`、`history.cancelFailed`
* 缺少 `history.retryConfirm` 和 `history.cancelConfirm` 翻译键

## Requirements

* 在 `handleRetry` 中添加 `window.confirm()` 确认，确认文案使用 `t("history.retryConfirm")`
* 在 `handleCancel` 中添加 `window.confirm()` 确认，确认文案使用 `t("history.cancelConfirm")`
* 在 en.json 和 zh-CN.json 中添加对应的翻译键

## Acceptance Criteria

* [ ] 点击重试按钮弹出确认对话框，确认后才执行重试
* [ ] 点击取消按钮弹出确认对话框，确认后才执行取消
* [ ] 卡片内联按钮和右键菜单两处触发均有确认
* [ ] 中英文翻译正确

## Definition of Done

* Lint / typecheck 通过
* 手动验证确认提示正常弹出

## Technical Approach

与 `handleDelete` 保持完全一致：在 handler 函数顶部加 `if (!window.confirm(t("history.xxxConfirm"))) return;`

## Out of Scope

* 自定义确认对话框组件（使用与项目一致的 `window.confirm`）
* 批量操作的确认
* 移除笔记标签的确认

## Technical Notes

* 涉及文件：`HistoryPage.tsx`、`en.json`、`zh-CN.json`
* 翻译键：`history.retryConfirm` / `history.cancelConfirm`
