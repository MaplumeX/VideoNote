# Fix: Milkdown editor shows raw markdown instead of rendered WYSIWYG

## Problem

The Milkdown note editor displays raw markdown source text (e.g., `# Heading`, `**bold**`) instead of rendering it as WYSIWYG formatted content. Headings, bold, lists, and all rich text formatting are invisible — users see the markdown source code verbatim.

## Root Cause

`NoteEditor.tsx` line 363 passes `remarkTimestampBadgePlugin` (the return value of `$remark()`) directly to `.use()`. The `$remark()` utility returns an array `[options, plugin]` — the actual Milkdown plugin is at `.plugin`, not the array itself.

Compare with the correct usage in `milkdown-katex.ts` and `milkdown-mermaid.ts`:
- `katexPlugins` includes `remarkMathPlugin.plugin` ✅
- `mermaidPlugins` includes `remarkMermaidDiagramPlugin.plugin` ✅
- `.use(remarkTimestampBadgePlugin)` — passes the **array** instead of the **plugin** ❌

When `.use()` receives the wrong type, editor initialization fails silently (errors caught by `.catch(console.error)` in the React binding), and ProseMirror never renders — leaving the raw markdown text visible.

## Fix

Change `.use(remarkTimestampBadgePlugin)` → `.use(remarkTimestampBadgePlugin.plugin)` in `NoteEditor.tsx` line 363.

## Scope

- Single line change in `frontend/src/components/NoteEditor.tsx`
- No other files affected
- No CSS changes needed (the custom `.milkdown-theme-nord` styles are correct and present in the build output)

## Verification

1. TypeScript compilation passes (`tsc --noEmit`)
2. Vite build succeeds
3. Visual: open a note in the browser — headings, bold, lists, etc. render as WYSIWYG, not raw markdown
