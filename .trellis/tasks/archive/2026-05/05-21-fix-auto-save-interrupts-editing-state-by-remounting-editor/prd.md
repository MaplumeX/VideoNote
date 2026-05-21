# fix: auto-save interrupts editing state by remounting editor

## Goal

Fix auto-save so it never interrupts the user's editing state (cursor position, IME composition, undo/redo history, focus). The editor should remain stable during background saves.

## What I already know

* Auto-save uses 1.5s debounce timer (`autoSaveTimerRef`) in `NoteDetailPage.tsx:172-179`
* `handleSave` on success calls `setEditMarkdown(savedNote.markdown)` (line 164) which triggers `NoteEditor`'s `markdown` prop change
* `NoteEditor.tsx:496-501` increments `editorKey` when `markdown` prop changes → destroys/remounts entire Milkdown editor
* Backend normalizes markdown via `normalize_note_markdown` (strips outer code fences) → saved content may differ from edited content → guarantees remount trigger
* `hasUnsavedChanges` currently compares `editMarkdown !== note.markdown` (line 56)

## Root Cause

`setEditMarkdown(savedNote.markdown)` after save causes unnecessary state update that propagates to `NoteEditor` as a `markdown` prop change, triggering full editor teardown/remount.

## Technical Approach

1. **Remove `setEditMarkdown(savedNote.markdown)` from save success handler** — prevents `markdown` prop from changing, so `NoteEditor` won't remount
2. **Add `lastSavedMarkdownRef`** to track what was last saved (set to `editMarkdownRef.current` after save success)
3. **Change `hasUnsavedChanges`** to compare against `lastSavedMarkdownRef.current` instead of `note.markdown`
4. Keep `setNote(savedNote)` for other purposes (title updates, sidebar display)

## Acceptance Criteria

- [ ] Auto-save does not cause editor remount (no cursor loss, no IME interruption, no undo history loss)
- [ ] `hasUnsavedChanges` still works correctly — shows "unsaved" when editing, clears after save
- [ ] Note switch still works correctly (editor loads new note content)
- [ ] Cmd/Ctrl+S manual save still works
- [ ] Save status indicator (Saving/Saved/Save failed) still works

## Definition of Done

- Manual testing: type in editor, wait for auto-save, verify cursor position preserved
- Lint / typecheck green
- No regressions in note switching

## Out of Scope

- Changing debounce timing
- Changing backend normalization behavior
- Adding "unsaved changes" indicator (already removed in previous PR)

## Technical Notes

* Key files: `NoteDetailPage.tsx`, `NoteEditor.tsx`
* `NoteEditor.tsx:496-501` — the effect that remounts editor on markdown prop change
* `NoteEditor.tsx:505` — `<MilkdownProvider key={editorKey}>`
* `NoteDetailPage.tsx:56` — `hasUnsavedChanges` derived state
* `NoteDetailPage.tsx:157-170` — `handleSave` callback
* `NoteDetailPage.tsx:172-179` — `handleEditorChange` debounce
