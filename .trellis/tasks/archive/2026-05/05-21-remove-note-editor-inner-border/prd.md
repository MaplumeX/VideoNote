# remove note editor inner border

## Goal

Remove the inner visual border/outline from the note content editor while keeping the outer note editor card border intact.

## What I already know

* The note detail page renders `NoteEditor` in the center content area.
* `NoteEditor` wraps Milkdown with an outer `rounded-xl border border-border bg-background p-6` container.
* Milkdown's `nord` config applies `prose dark:prose-invert milkdown-theme-nord` to the ProseMirror editable root.
* The user wants to remove the inner layer, not the outer card border.

## Assumptions

* The desired outcome is a single visible border around the note content area.
* Editing behavior, formatting, timestamps, KaTeX, Mermaid, and slash command behavior should not change.

## Requirements

* Keep the outer `NoteEditor` container border.
* Remove the inner Milkdown/ProseMirror border, outline, and shadow visual treatment.
* Preserve focus and editing behavior.
* Keep the change scoped to frontend styling.

## Acceptance Criteria

* [x] The note content area shows only one outer border in normal state.
* [x] Focusing/clicking inside the editor does not show a second inner border.
* [x] Existing Milkdown content styling remains intact.
* [x] Frontend lint/type-check/build checks pass where practical.

## Definition of Done

* Frontend coding guidelines reviewed.
* Minimal scoped CSS change implemented.
* Relevant frontend verification command run.

## Out of Scope

* Redesigning the note detail layout.
* Removing borders from tables, code blocks, Mermaid diagrams, or other Markdown content elements.
* Changing editor behavior or Milkdown plugins.

## Technical Notes

* Likely files: `frontend/src/index.css`, optionally `frontend/src/components/NoteEditor.tsx`.
* Use CSS targeting the Milkdown/ProseMirror root instead of changing component hierarchy.
