# Remove save button (auto-save replaces it)

## Goal

Remove the manual "Save" button from NoteDetailPage sidebar since auto-save with 1.5s debounce already handles persistence.

## What I already know

* Auto-save implemented in commit 1a52964: 1.5s debounce on editor change, Cmd+S shortcut for immediate save
* Save button rendered in NoteDetailPage.tsx lines 320-336, with saving/save-failed/saved status messages below
* `Save` icon imported from lucide-react (line 12)
* `handleSave`, `saving`, `saveError` state are shared between manual save and auto-save — these must be kept
* SettingsPage.tsx also has a save button — this is for saving settings, NOT note content; must NOT be removed
* Cmd+S keyboard shortcut should remain as an escape hatch for immediate save

## Assumptions

* The Cmd+S shortcut is sufficient as a manual override — no need for any other save trigger
* Save status feedback (saving/saved/failed) should be kept but moved to a less intrusive indicator (no longer a button area)

## Decisions

* Save status: keep a lightweight indicator (small text) in the sidebar showing saving/saved/failed — replaces the button area, not adds to it

## Requirements

* Remove the Save `<Button>` element from NoteDetailPage sidebar
* Replace the old button+status block with a lightweight save status indicator (small text: saving / saved / failed)
* Remove the `Save` icon import if no longer used elsewhere in this file
* Keep `handleSave`, `saving`, `saveError`, `hasUnsavedChanges` — still used by auto-save
* Keep Cmd+S shortcut
* Do NOT touch SettingsPage save button

## Acceptance Criteria

* [ ] No Save button visible in NoteDetailPage sidebar
* [ ] Lightweight save status indicator shows: "Saving..." / "Saved" / "Save failed"
* [ ] Auto-save still works (1.5s debounce on edit)
* [ ] Cmd+S still triggers immediate save
* [ ] Settings page save button unchanged
* [ ] No dead imports or unused variables left behind

## Definition of Done

* Lint / typecheck green
* No dead code from the removal

## Out of Scope

* Settings page save button
* Changing auto-save debounce timing
* Adding a new save status indicator (unless trivial)

## Technical Notes

* Key file: `frontend/src/pages/NoteDetailPage.tsx`
* Lines to remove: ~320-336 (button + status messages)
* Lines to check: import of `Save` icon (line 12) — only remove if unused in this file
