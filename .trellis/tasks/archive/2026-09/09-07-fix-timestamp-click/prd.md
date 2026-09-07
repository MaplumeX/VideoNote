# Fix timestamp badge not clickable in note editor

## Goal

修复笔记详情页中时间戳徽章（timestamp badge）无法点击跳转视频播放进度的问题。用户看到的是可点击样式（高亮、cursor-pointer），但点击无任何反应。

## Background / Root Cause

`frontend/src/components/NoteEditor.tsx` 中的 `TimestampBadgeView`（ProseMirror NodeView）存在两个缺陷：

1. **事件被编辑器拦截（主因）**：徽章按钮位于 Milkdown/ProseMirror 可编辑区域内。NodeView DOM 上监听的是原生 `click` 事件，而 ProseMirror 会接管可编辑区内的 mousedown/click 用于选区与光标定位，导致按钮上的 `click` 监听收不到事件或交互被吞掉。ProseMirror 官方推荐在 NodeView DOM 上监听 `mousedown` 并 `preventDefault()` + `stopPropagation()` 来实现自定义点击交互。
2. **状态快照过期（次因）**：`hasVideo` / `onTimestampClick` 依赖 `fetchTaskById` 异步结果。NodeView 构造时读取模块级变量 `_timestampHasVideo` / `_timestampClickHandler` 的一次性快照来决定样式与是否挂监听；之后 `setTimestampContext()` 更新模块变量不会刷新已渲染的徽章。当数据先于视频信息加载完成时，徽章以可点样式渲染但处理器可能为 null 或反过来。

## Requirements

- 时间戳徽章在有视频（`hasVideo === true`）时点击可跳转：打开/复用浮动播放器并 seek 到对应秒数。
- 点击交互必须在 Milkdown 编辑器内正常工作，不被 ProseMirror 选区/光标逻辑拦截。
- 徽章样式必须与当前 `hasVideo` 状态一致：无视频时灰色不可点，有视频时高亮可点；异步加载完成后已渲染的徽章样式要正确刷新。
- 不破坏现有 markdown 序列化（`#t=seconds` 链接 ↔ timestamp-badge 节点的互转）。
- 不破坏编辑器其他功能（slash 菜单、自动保存、TOC 等）。

## Acceptance Criteria

- [ ] 打开一个含视频（YouTube/Bilibili）的笔记详情页，等待任务信息加载完成后，点击时间戳徽章：浮动播放器打开并从对应时间点播放。
- [ ] 播放器已打开时再次点击另一个时间戳，播放器 seek 到新时间点（iframe 重建加载新 start 参数）。
- [ ] 无视频的笔记中时间戳徽章为灰色不可点样式，点击无反应。
- [ ] 在编辑器中正常编辑文本（含时间戳徽章前后）不受影响；markdown 保存后 `#t=` 链接格式不变。
- [ ] 现有前端测试全部通过（`npm test` / vitest）。

## Notes

- Lightweight bug fix，PRD-only。
- 涉及文件：`frontend/src/components/NoteEditor.tsx`（TimestampBadgeView / setTimestampContext）。
- 如需为交互行为补一条组件级测试（时间戳点击 → onTimestampClick 调用）更好，但不强制。
