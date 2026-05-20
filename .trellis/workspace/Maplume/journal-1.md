# Journal - Maplume (Part 1)

> AI development session journal
> Started: 2026-05-17

---



## Session 1: VideoNote MVP: AI video note summarizer (backend + frontend)

**Date**: 2026-05-17
**Task**: VideoNote MVP: AI video note summarizer (backend + frontend)
**Branch**: `main`

### Summary

Built VideoNote MVP — a web app that takes video URLs (YouTube/Bilibili) or local files, extracts content (subtitle-first with ASR fallback via OpenAI Whisper), and generates structured Markdown notes with timestamps via LLM. Stack: FastAPI + ARQ (Redis) + yt-dlp + ffmpeg backend, Vite + React 19 + Tailwind + react-markdown frontend, SSE for progress. Quality check fixed 8 issues (path traversal, file type validation, URL platform check, React render-during-setState, SSE stale closure, props spread, video title extraction). Updated 8 spec files with project conventions.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0f7a55a` | (see git log) |
| `e33562b` | (see git log) |
| `60411d1` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: Remove Redis: replace ARQ+Redis with SQLite+asyncio

**Date**: 2026-05-17
**Task**: Remove Redis: replace ARQ+Redis with SQLite+asyncio
**Branch**: `feat/remove-redis`

### Summary

Removed Redis/ARQ dependencies. Task queue replaced by asyncio.create_task in-process. Task state migrated from Redis Hash to SQLite (WAL mode, aiosqlite). Sync blocking calls wrapped with asyncio.to_thread(). File cleanup moved to finally block. Deleted worker.py.


## Session 3: Support custom ASR/LLM providers

**Date**: 2026-05-17
**Task**: Support custom ASR/LLM providers
**Branch**: `feat/llm-provider`

### Summary

Add independent ASR_API_KEY/ASR_API_BASE/ASR_MODEL and LLM_API_KEY env vars with backward-compatible fallback to OPENAI_API_KEY/OpenAI defaults

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `bb993fc` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: Support SiliconFlow as ASR Provider

**Date**: 2026-05-17
**Task**: Support SiliconFlow as ASR Provider
**Branch**: `feat/siliconflow-transcription`

### Summary

Added ASR_PROVIDER env var (openai/siliconflow). SiliconFlow mode sends only file+model params, uses 50MB limit, returns plain text. OpenAI mode unchanged.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `6ca7a27` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: Add i18n internationalization support (en + zh-CN)

**Date**: 2026-05-17
**Task**: Add i18n internationalization support (en + zh-CN)
**Branch**: `feat/add-i18n`

### Summary

为 VideoNote 添加 i18n 支持：前端 react-i18next + 浏览器语言检测 + Header 切换按钮；后端 language 参数 + prompt 模板按语言组织。初始支持 en/zh-CN。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `85cb9be` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: Add yt-dlp proxy support

**Date**: 2026-05-17
**Task**: Add yt-dlp proxy support
**Branch**: `main`

### Summary

Added YT_DLP_PROXY env var to config.py; created _ydl_opts() helper in subtitle.py for unified proxy injection; updated audio.py to reuse _ydl_opts; added proxy example to .env.example

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `25960ef` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: Implement user authentication system

**Date**: 2026-05-18
**Task**: Implement user authentication system
**Branch**: `feat/user-system`

### Summary

Full user-system implementation: JWT + bcrypt auth with refresh token rotation, reuse detection, protected API routes, frontend login/register/history pages, route guards, authFetch with 401 auto-refresh, i18n for auth pages, CORS tightening. Quality check: fixed duplicate security declaration, unused vars, hardcoded strings, delayed imports; updated backend/frontend specs.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `71de18e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: Add provider/model selection settings page

**Date**: 2026-05-18
**Task**: Add provider/model selection settings page
**Branch**: `Feat/provider-model-selector`

### Summary

Full-stack provider/model selection feature: settings page (/app/settings) with ASR+LLM provider dropdown (presets + custom), API key stored encrypted in DB with Fernet, key masking in response, fallback to env vars, runtime params for transcribe/generate services.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `5e76601` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: Bootstrap Guidelines: fill .trellis/spec with project conventions

**Date**: 2026-05-18
**Task**: Bootstrap Guidelines: fill .trellis/spec with project conventions
**Branch**: `main`

### Summary

Populated all spec files under .trellis/spec/ with real codebase patterns. Filled 3 blank files (backend database-guidelines, logging-guidelines; frontend state-management). Updated 6 existing specs to remove stale ARQ/Redis references and add missing modules (auth, crypto, auth_routes, pages, i18n, auth). All index files updated from 'To fill' to 'Active'. Archived bootstrap task.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `4f7614b` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 10: Enhance task features: delete, retry, cancel, pagination, metadata

**Date**: 2026-05-18
**Task**: Enhance task features: delete, retry, cancel, pagination, metadata
**Branch**: `Feat/enhance-task-feature`

### Summary

Added 5 enhancements to the task system: hard delete (DELETE /api/tasks/{id}), retry for failed URL tasks (POST /tasks/{id}/retry), cancel with mark-cancel approach (POST /tasks/{id}/cancel), offset pagination (GET /api/tasks?page=N&limit=N), and metadata storage (video_url, file_name, platform, language, source_type). Backend: schemas, db migrations, 3 new endpoints. Frontend: HistoryPage rewrite with action buttons, metadata display, pagination, i18n for en/zh-CN. Check fixes: cancelled state overwrite protection, delete_task user_id defense-in-depth, cross-layer type consistency, progress bar visualization.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `f2bc5ac` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 11: Fix SSE CRLF parsing causing white screen

**Date**: 2026-05-18
**Task**: Fix SSE CRLF parsing causing white screen
**Branch**: `fix/fix-white-screen-after-video-submit`

### Summary

Fixed white screen after video submit: useSSE.ts used line === '' to detect SSE event boundaries, but sse-starlette sends \r\n line endings, making empty lines become '\r' instead of ''. Changed to line.trim() === '' for cross-line-ending compatibility. Updated frontend hook-guidelines spec with the gotcha.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `9f77489` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 12: Fix auth refresh: silent refresh on app startup

**Date**: 2026-05-19
**Task**: Fix auth refresh: silent refresh on app startup
**Branch**: `Feat/fix-auth-persist-login`

### Summary

修复页面刷新后用户被踢回登录页的问题。access token 仅存内存，刷新后丢失，而 refresh cookie 有效却未被使用。在 main.tsx 的 bootstrap() 中 router 创建前调用 silentRefresh()，用 httpOnly cookie 恢复 access token。质量检查发现 top-level await 在 Vite esbuild 中不可用，改为 async function 包装。更新了 state-management spec 记录此模式。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `adbc91b` | (see git log) |
| `a67ba7e` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 13: Fix Bilibili yt-dlp audio download FileNotFoundError

**Date**: 2026-05-19
**Task**: Fix Bilibili yt-dlp audio download FileNotFoundError
**Branch**: `main`

### Summary

Fix yt-dlp Bilibili audio download failure: check download() return code, override quiet=False for error visibility, expand file matching to handle extensionless files, add diagnostic logging.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `ea25d86` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 14: Refactor UI from tool to software feel

**Date**: 2026-05-19
**Task**: Refactor UI from tool to software feel
**Branch**: `Feat/online-software-look`

### Summary

Replaced single-page tool layout with multi-route software experience: sidebar navigation, dashboard homepage, independent note creation/detail flow with SSE progress recovery, and card-based history archive. Backend: added title field to TaskListItem parsed from result_json. Frontend: new Sidebar, DashboardPage, NewNotePage, NoteDetailPage; rewrote AppLayout and HistoryPage; removed dead VideoNoteApp.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `eba1d4f` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 15: Move language switch to Settings page

**Date**: 2026-05-19
**Task**: Move language switch to Settings page
**Branch**: `Feat/put-lang-switch-in-settings`

### Summary

Moved language toggle from sidebar click-button to a dropdown select in Settings page. Extracted shared style constants (selectClass/inputClass/labelClass) to module level.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `79c2551` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 16: Polish frontend UI with shadcn/ui, dark mode, and layout fix

**Date**: 2026-05-19
**Task**: Polish frontend UI with shadcn/ui, dark mode, and layout fix
**Branch**: `Feat/optimize-frontend-ui`

### Summary

引入 shadcn/ui (base-nova) 统一设计语言，修复侧边栏全高布局，添加深色模式切换，提取共享 StatusBadge，将所有原生 button/input/select 迁移到 shadcn/ui 组件，更新 CSS 主题到 oklch 色彩空间

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `00f1cbd` | (see git log) |
| `86f3d3c` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 17: Fix UI quality issues

**Date**: 2026-05-19
**Task**: Fix UI quality issues
**Branch**: `Feat/fix-ui-layout-and-menus`

### Summary

Fixed 4 UI quality issues: sidebar overlapping main content on desktop, language selector showing raw value code instead of display label, Select dropdown menus misaligned on mobile, and missing @tailwindcss/typography plugin causing unstyled markdown in NoteView.


## Session 18: Optimize note feature — tags, folders, favorites, WYSIWYG editor, enhanced markdown preview

**Date**: 2026-05-19
**Task**: Optimize note feature — tags, folders, favorites, WYSIWYG editor, enhanced markdown preview
**Branch**: `Feat/optimize-md-preview`

### Summary

Implemented 4 PRs: (1) backend tags/folders/favorites CRUD API + DB schema, (2) frontend ContentSidebar + HistoryPage filtering, (3) Milkdown WYSIWYG editor with TimestampBadge node + slash commands + edit/preview toggle, (4) Shiki dual-theme code highlighting + TOC sidebar + KaTeX math + Mermaid diagrams + ThemeProvider context + @tailwindcss/typography. Updated frontend specs with new patterns.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `0247ec2` | (see git log) |
| `6613e19` | (see git log) |
| `e040b13` | (see git log) |
| `dae0ad6` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 19: Optimize new note page UI

**Date**: 2026-05-19
**Task**: Optimize new note page UI
**Branch**: `style/optimize-new-note-ui`

### Summary

Optimized new note page: added hero section, merged URL+upload into single view, enriched drag zone visuals, replaced progress bar with 3-step indicator, synced NoteDetailPage progress display.


## Session 20: 优化历史界面 UI 布局

**Date**: 2026-05-19
**Task**: 优化历史界面 UI 布局
**Branch**: `style/optimize-history-ui`

### Summary

History page UI overhaul: view toggle (card/list), search with debounce, sort by title/stage/created_at, batch action bar, context menu, pagination, Sheet-based filters. Fixed: search now matches title in result_json, sort_by=title uses json_extract, inline styles replaced with CSS custom properties + Tailwind, useEffect dependency stabilized. Updated 3 code-spec docs with learned patterns.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a6404fc` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 21: Unify note rendering to Milkdown-only + 3-column layout

**Date**: 2026-05-19
**Task**: Unify note rendering to Milkdown-only + 3-column layout
**Branch**: `Feat/optimize-note-ui-render`

### Summary

Replaced react-markdown preview pipeline with Milkdown WYSIWYG-only rendering. Added custom ProseMirror node plugins for KaTeX math (milkdown-katex.ts) and Mermaid diagrams (milkdown-mermaid.ts). Integrated prism, katex, mermaid into NoteEditor. Removed 6 unused deps. Restructured NoteDetailPage to 3-column layout: left sidebar (actions/tags/folder), center full-width editor, right TOC. Replaced inline styles with CSS custom property + Tailwind arbitrary value pattern. Updated component-guidelines and directory-structure specs.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `cf87158` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 22: 升级时间戳：条件渲染 + 悬浮视频跳转

**Date**: 2026-05-19
**Task**: 升级时间戳：条件渲染 + 悬浮视频跳转
**Branch**: `Feat/upgrade-timestamp-video-seek`

### Summary

后端条件化 LLM prompt 避免无时间戳时的幻觉；前端新增 VideoPlayerFloat 悬浮播放器（拖拽/缩放/最小化/关闭），时间戳 badge 有视频时可点击 seek，无视频时灰显不可点击；NoteDetailPage 集成播放入口和跳转逻辑。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3295cde` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 23: Fix note rendering and dark mode theme

**Date**: 2026-05-20
**Task**: Fix note rendering and dark mode theme
**Branch**: `fix/fix-note-render-and-theme`

### Summary

Replaced @milkdown/theme-nord/style.css (which contained a Tailwind v4 reset layer breaking WYSIWYG rendering and used prefers-color-scheme for dark mode) with custom .milkdown-theme-nord CSS using project CSS variables and .dark class. Switched prism theme to prism-tomorrow, added KaTeX dark mode override, removed orphan .dark .prose rules.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `e622ba2` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 24: Fix Milkdown raw markdown rendering

**Date**: 2026-05-20
**Task**: Fix Milkdown raw markdown rendering
**Branch**: `Feat/fix-note-style-rendering`

### Summary

Fixed Milkdown editor showing raw markdown instead of WYSIWYG: changed .use(remarkTimestampBadgePlugin) to .use(remarkTimestampBadgePlugin.plugin). The $remark() utility returns [options, plugin] tuple; passing the raw tuple to .use() caused silent editor initialization failure.


## Session 24: Sidebar Collapsible Feature

**Date**: 2026-05-20
**Task**: Sidebar Collapsible Feature
**Branch**: `Feat/sidebar-collapsible`

### Summary

Implemented desktop sidebar collapse to icon mode with Tooltip, Cmd/Ctrl+B shortcut, and localStorage persistence. Updated component spec with @base-ui render prop guidance.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a71fcb7` | (see git log) |
| `c8217dc` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
