# 笔记自动保存 (autosave)

## Goal

为笔记编辑器添加自动保存功能，用户编辑笔记后无需手动点击保存按钮，内容会自动持久化到后端。

## What I already know

* 当前保存机制：手动保存（Save 按钮 + Cmd/Ctrl+S），位于 `NoteDetailPage.tsx`
* 编辑器：Milkdown (ProseMirror-based WYSIWYG)，每次按键都触发 `onChange` 更新 `editMarkdown` state
* 脏检测：简单字符串比较 `editMarkdown !== note.markdown`
* API：`PUT /api/tasks/{jobId}/content` 发送 `{ markdown: string }`
* 保存互斥：`saving` flag 防止重复保存，无队列/重试
* 错误处理：`handleSave` 静默吞错误
* 所有状态在 `NoteDetailPage` 本地 useState，无全局 store

## Assumptions (temporary)

* 自动保存使用 debounce 方式（而非定时轮询）
* debounce 间隔 1.5 秒

## Requirements

* 编辑内容变更后自动保存到后端（debounce 1.5s）
* 保留手动保存入口（Save 按钮 + Cmd/Ctrl+S）
* 手动保存立即触发（取消待执行的 debounce，直接保存）
* 侧边栏切换笔记时，如有未保存内容立即保存后再切换
* 页面关闭/刷新时 beforeunload 提示未保存内容
* 保存失败时 UI 显示错误状态，下次输入变更时重试自动保存

## Acceptance Criteria

* [ ] 停止输入 1.5 秒后自动触发保存 API
* [ ] 手动保存（Cmd+S / 按钮）立即触发，跳过 debounce 等待
* [ ] 自动保存进行中时手动保存不重复请求（saving 互斥）
* [ ] 侧边栏切换到其他笔记时，当前笔记未保存内容先 flush 保存
* [ ] 页面关闭/刷新时如有未保存内容触发 beforeunload 提示
* [ ] 保存失败时 UI 显示错误状态，下次编辑变更时重试

## Definition of Done

* Lint / typecheck 通过
* 手动验证自动保存功能正常
* 边缘情况处理合理

## Out of Scope (explicit)

* 离线编辑 / 本地缓存
* 多设备冲突解决
* 版本历史

## Technical Notes

* 主要文件：`frontend/src/pages/NoteDetailPage.tsx`
* 编辑器组件：`frontend/src/components/NoteEditor.tsx`
* API：`frontend/src/api/client.ts` — `updateNoteContent()`
