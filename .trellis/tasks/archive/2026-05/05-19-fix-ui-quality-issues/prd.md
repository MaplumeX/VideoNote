# PRD: Fix UI Quality Issues

## Problem
Current UI has multiple quality issues: misalignment, content hidden behind sidebar, dropdown menus not adapting properly, and language selector showing raw value code instead of display label.

## Identified Issues

1. **Language selector shows "zh-CN" instead of "中文"**
   - `SelectValue` from `@base-ui/react` renders raw value prop text
   - `LANG_LABELS` mapping used only in `SelectItem` children, not in trigger display
   - Fix: override SelectValue display with label lookup

2. **Main content overlaps fixed sidebar on desktop**
   - Sidebar is `fixed w-52` (208px), main content has no left margin
   - Content `max-w-5xl mx-auto` centers in full viewport width, not accounting for sidebar
   - On screens 1024-1440px, content partially hidden behind sidebar
   - Fix: add `md:ml-52` to main content wrapper

3. **Select dropdown menus not adapting on mobile**
   - `SelectContent` uses `w-(--anchor-width)` matching trigger width
   - On mobile, dropdown may overflow viewport or clip
   - `align="center"` + `alignItemWithTrigger=true` can cause odd positioning
   - Fix: set `align="start"` and `alignItemWithTrigger=false` for better mobile behavior; add min-width constraints

4. **Missing `@tailwindcss/typography` plugin**
   - `NoteView` uses `prose prose-sm` classes but plugin not installed
   - Markdown content renders unstyled
   - Fix: install and add `@tailwindcss/typography` plugin

## Scope
- Frontend only
- No backend changes
- No new features, only fixes

## Out of Scope
- Dark mode color adjustments
- New pages or components
