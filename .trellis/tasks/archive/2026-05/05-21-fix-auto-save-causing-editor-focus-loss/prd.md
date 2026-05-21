# fix auto-save causing editor focus loss

## Goal

修复自动保存后 Milkdown 编辑器失去焦点/退出编辑态的问题，使用户在编辑过程中不被打断。

## What I already know

* 根因（双重触发）：
  1. `NoteEditor.tsx:496-501` — `markdown` prop 变化时 `editorKey` 递增 → `MilkdownProvider key` 变化 → 编辑器卸载重建
  2. `NoteEditor.tsx:378` — `useEditor` 依赖 `[markdown]` → markdown 变化时 Milkdown 销毁旧 Editor + 重建新 Editor
* 用户编辑触发链：`handleEditorChange` → `setEditMarkdown(value)` → `markdown` prop 变化 → 两条路径都触发重建
* 后端 `normalize_note_markdown` 会剥离外层 code fence，可能导致保存后返回的 markdown 与编辑器内容不同
* #31 修复避免了 `handleSave` 中 `setEditMarkdown(savedNote.markdown)`，但没解决编辑过程中的重建问题
* Milkdown v7 `useEditor` deps 变更 → `editor.destroy()` → `EditorView.destroy()` → 完整 DOM/事件/状态销毁，焦点/光标/IME/undo 全部丢失

## Requirements

* 用户编辑过程中，自动保存不得导致编辑器重建或焦点丢失
* 外部 markdown 变更（切换笔记、SSE 完成）仍需正确重建编辑器
* 自动保存后端返回的 markdown 若与编辑器内容不同（因 normalize），不能覆盖编辑器内容
* IME 输入法组合状态、光标位置、undo/redo 历史在自动保存时必须保持

## Acceptance Criteria

* [ ] 编辑状态下自动保存后，编辑器仍保持焦点，光标位置不变
* [ ] 连续输入 1.5s 后触发自动保存，不中断输入
* [ ] 切换笔记时编辑器正确加载新内容
* [ ] SSE 处理完成后编辑器正确加载新内容
* [ ] Cmd+S 手动保存不中断编辑

## Definition of Done

* Lint / typecheck / CI green
* 手动验证上述场景

## Technical Approach

**方案：用 `resetKey` 显式控制编辑器重建，解除对 markdown prop 变化的隐式依赖**

核心思路：编辑器何时重建应由父组件显式决定，而非 `NoteEditor` 自己猜测 markdown 变化来源。

具体改动：

1. **`NoteEditor` 接受 `resetKey` prop** 替代内部 markdown diff 机制
   - 删除 `editorKey` state 和 `markdown !== prevMarkdownRef.current` useEffect
   - `MilkdownProvider key={resetKey}` — 仅当父组件递增 resetKey 时重建

2. **`useEditor` 移除 `[markdown]` 依赖**
   - 改为 `[]`，通过 ref 读取 markdown 初始值
   - 因为 `MilkdownProvider key` 变化会完全卸载/重建子树，`useEditor` 会重新执行，不需要 dep 驱动

3. **`NoteDetailPage` 管理 `resetKey`**
   - 新增 `editorResetKey` state，初始值 0
   - 仅在两个场景递增：切换笔记 (jobId 变化)、SSE 完成加载新内容
   - 不在 `handleEditorChange` 或 `handleSave` 时递增

## Out of Scope

* 重构 debounce 实现
* 修改后端 normalize 逻辑
* 添加自动保存的单元测试

## Technical Notes

* 关键文件：
  - `frontend/src/components/NoteEditor.tsx` — editorKey 机制 (L488-509), useEditor deps (L378)
  - `frontend/src/pages/NoteDetailPage.tsx` — handleEditorChange (L175-182), handleSave (L160-173)
  - `backend/app/services/markdown.py` — normalize_note_markdown (L13)
* Milkdown v7.21.x — `useEditor` deps 变更导致完整 Editor destroy+rebuild（已验证源码）
