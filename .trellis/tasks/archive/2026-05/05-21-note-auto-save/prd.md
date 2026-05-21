# Note Auto-Save

## Goal

笔记编辑时自动保存，用户停止输入 1.5 秒后自动触发保存，避免内容丢失。

## Requirements

* 用户停止输入 1.5 秒后自动保存笔记内容到后端
* 保存状态可见（已保存 / 正在保存 / 保存失败）
* Cmd/Ctrl+S 仍可手动保存（立即保存，取消待执行的 debounce）
* 切换笔记时取消未执行的 debounce 保存

## Acceptance Criteria

* [ ] 编辑后停止输入 1.5 秒，自动触发保存 API
* [ ] 保存状态有视觉指示（"已保存" / "保存中..." / "保存失败"）
* [ ] Cmd/Ctrl+S 立即保存并取消待执行的 debounce 定时器
* [ ] 切换笔记时清理 debounce 定时器，不会把旧笔记内容保存到新笔记

## Definition of Done

* Lint / typecheck 通过
* 手动验证自动保存行为

## Technical Approach

在 NoteDetailPage.tsx 中：
1. 用 `useRef` 持有 debounce 定时器
2. `onChange` 回调中：更新 `editMarkdown` + 重置 1.5 秒 debounce 定时器
3. debounce 回调中调用 `handleSave()`
4. 手动保存时先清除 debounce 定时器再保存
5. 用 `useEffect` cleanup 在切换笔记时清除定时器
6. 保存状态指示：替换现有 "unsaved" 文本为三态指示器

## Decision (ADR-lite)

**Context**: 需要 debounce 延迟时长
**Decision**: 1.5 秒
**Consequences**: 比 2 秒更及时，比 1 秒更少无效请求

## Out of Scope

* 版本历史 / 版本回退
* 离线保存队列
* beforeunload / 路由离开守卫

## Technical Notes

* 核心文件：frontend/src/pages/NoteDetailPage.tsx
* API：frontend/src/api/client.ts → updateNoteContent()
* 已有 debounce 模式参考：frontend/src/pages/HistoryPage.tsx
* 项目 debounce 规范：.trellis/spec/frontend/state-management.md
