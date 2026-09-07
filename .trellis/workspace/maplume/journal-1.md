# Journal - maplume (Part 1)

> AI development session journal
> Started: 2026-07-23

---



## Session 1: 修复核心链路七项可靠性缺陷

**Date**: 2026-07-23
**Task**: 修复核心链路七项可靠性缺陷
**Branch**: `main`

### Summary

完成自动保存快照串行化、上传语言契约、SSE 增量解析与断线兜底、SQLite 单进程任务恢复、鉴权刷新 single-flight、任务持久取消和标签用户边界；新增前后端回归测试并更新 Trellis 规范。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `fc9cefd` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 修复核心链路进度反馈与取消恢复可靠性

**Date**: 2026-07-24
**Task**: 修复核心链路进度反馈与取消恢复可靠性
**Branch**: `main`

### Summary

修复核心链路八项缺陷：进度单调不减（URL 无字幕回落与上传音频提取语义）、前端实时展示 progress.message、失败步骤按 progress 阈值定位、cancel_event 深入 yt-dlp/ffmpeg/ASR/LLM 阻塞调用、恢复任务 attempt 上限 5、长视频笔记分 chunk 进度上报与 finish_reason=length 截断续写、同 URL 重复提交去重、/models 与上传音频失败错误码不泄漏。后端 43 + 前端 34 测试全绿。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `f25cf1f` | (see git log) |
| `e7c3bbe` | (see git log) |
| `3dda607` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: 修复核心链路逻辑 bug 与体验问题(13 项)

**Date**: 2026-07-24
**Task**: 修复核心链路逻辑 bug 与体验问题
**Branch**: `main`

### Summary

代码审查发现核心链路 13 项问题(逻辑 bug + 体验 + 代码异味),分 6 阶段(Phase A–F)全部修复。后端 57 + 前端 40 = 97 测试全绿,ruff/eslint clean,trellis-check 独立审查通过 12/12 AC。

### Main Changes

- **Phase A+B(后端契约+helper 抽取)**:`ProcessResponse`/`UploadResponse` 增 `source_type` 字段;dedup 分支返回 DB title/thumbnail;新增 `ProviderBundle`/`_resolve_providers`/`_StageFailed`/`_run_asr`/`_run_note_gen`/`_make_asr_progress_cb`/`_make_note_progress_cb`,消除 `_process_video_url`/`_process_video_file` 大段重复。
- **Phase C(错误透传+provider 校验)**:`_sanitize_error_detail` 剥离 sk-*/Bearer/cookie 并截断 200 字;失败 message 写 `"CODE: detail"`(detail 为空退化纯 code);`_ensure_providers_configured` 在 /process /upload /retry 前置校验返回 422 `PROVIDER_NOT_CONFIGURED`。
- **Phase D(ASR 语言+取消+字幕去重)**:`_asr_language` 查表 {zh,en,ja}+None 自动探测;`transcribe_audio` 接受 `language: str | None`;`get_video_info_strict`/`extract_subtitles` 增 cancel_event 检查点;`extract_subtitles` 重构为单次 download 调用,删除 `extract_info(download=False)` 探测与 `_download_and_read_subtitle`。
- **Phase E(retry 拷贝+safe_name 加固)**:`retry_task` upload 分支 `shutil.copy2` 拷贝输入文件;`_sanitize_upload_name` 白名单正则替换。
- **Phase F(前端)**:useSSE 收到首事件后 `reconnectAttempt` 归零 + fetchTaskById 恢复后不消耗配额;useVideoUpload 401 silentRefresh 成功后自动重发(闭包标志防循环);NewNotePage 用 `data.source_type` 替代硬编码、fetchTaskById 拉取 title/thumbnail、PROVIDER_NOT_CONFIGURED 显示设置页按钮;translateTaskMessage 前缀匹配 `"CODE: detail"`。
- **Spec 更新**:backend error-handling.md(PROVIDER_NOT_CONFIGURED + detail 透传格式);frontend hook-guidelines.md(upload 401 auto-replay 契约);cross-layer guide(initiating page late-metadata fetch 模式)。

### Git Commits

| Hash | Message |
|------|---------|
| `d84fcc2` | fix(core): resolve pipeline logic bugs and UX issues across 13 areas |

### Testing

- Backend: `uv run pytest -q` → 57 passed
- Frontend: `npm test -- --run` → 40 passed (7 files)
- Lint: `ruff check .` clean, `eslint .` clean, `vite build` OK
- trellis-check 独立审查:12/12 AC 满足,无阻塞

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: Fix duplicate yt-dlp downloads in _to_thread_with_cancel

**Date**: 2026-09-02
**Task**: Fix duplicate yt-dlp downloads in _to_thread_with_cancel
**Branch**: `fix/bilibili-cookie-download-403`

### Summary

Diagnosed Bilibili 403/FileNotFoundError during audio download: _to_thread_with_cancel created a new asyncio.to_thread future inside its polling loop, re-dispatching the blocking call every 3s and spawning concurrent yt-dlp threads writing the same audio.m4a.part. Fixed by creating the future once and adding a _cancel_watcher for prompt cancellation; added 5 regression tests (exactly-once execution verified to fail on old code, 74 tests pass, ruff clean). Cookie handling itself was working correctly.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `f5b0e3f` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: Review core pipeline and fix P0/P1 bugs

**Date**: 2026-09-02
**Task**: Review core pipeline and fix P0/P1 bugs
**Branch**: `review/core-pipeline-bugs`

### Summary

Read-only review of the core pipeline (task lifecycle, subtitle/audio/ASR/note-gen stages, SPA serving) found 2 P0 + 4 P1 bugs; then fixed all six with regression tests: (P0) process_ie_result dict misused as yt-dlp retcode broke every no-subtitle ASR-fallback task; SPA fallback percent-decoded path traversal allowed unauthenticated arbitrary file reads. (P1) leaked partial files on upload disconnect; Retry button shown for cancelled tasks; cleanup cutoffs used isoformat against CURRENT_TIMESTAMP created_at (deleted tasks ~1 day early); random SECRET_KEY silently invalidated encrypted provider keys/cookies after restart. Backend 91 tests + frontend 43 tests pass, ruff clean; pitfalls recorded in backend specs. P2 findings documented in the review and left for future tasks.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `2488f96` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: C1 pipeline state machine & persistence (contract baseline)

**Date**: 2026-09-05
**Task**: C1 pipeline state machine & persistence (contract baseline)
**Branch**: `refactor/rewrite-core-pipeline`

### Summary

Rewrote planning for core pipeline rewrite (parent + 5 child tasks, architecture-upgrade option approved). Implemented C1: app/pipeline package (TaskStatus/PipelinePhase state machine with transition table, 15-code ErrorCode with sanitize-on-construct PipelineError, two-level progress model, Stage/ArtifactStore protocols), incremental DB migration (5 new task columns + backfill, task_artifacts table, conditional checkpoint writes), docs/pipeline-contract.md frozen at G1 gate. 173 tests passed, legacy pipeline untouched.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `a75548f` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: C2+C3 transcription & note-gen stages (parallel)

**Date**: 2026-09-05
**Task**: C2+C3 transcription & note-gen stages (parallel)
**Branch**: `refactor/rewrite-core-pipeline`

### Summary

Implemented C2 and C3 in parallel against the frozen C1 contract: subprocess_util (managed killable subprocesses, centralized yt-dlp CLI args, error classification), stages fetch/subtitle/audio/transcribe/notegen (Async[OI] clients, verbatim semantic migration of subtitle parsing, ASR chunking, LLM prompts/retry/continuation), StageContext/StageResult extra fields. 100 new tests incl. real-subprocess cancel proof (<3s, no residual); suite at 274 passed. Check agents fixed WAV concurrency overwrite (per-job filenames) and a test anti-pattern; C3 clean.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `5293c92` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: C4 orchestrator & API layer switchover

**Date**: 2026-09-06
**Task**: C4 orchestrator & API layer switchover
**Branch**: `refactor/rewrite-core-pipeline`

### Summary

Implemented C4 (three relayed implement agents + check + approved patch): state-machine orchestrator with checkpoint resume/recovery matrix/retry, asyncio-native runner, routes.py rewritten to 450-line thin API layer with ProgressEvent SSE, legacy chain (task_runner + 4 services + 7 old test files) deleted. Check agent fixed 5 substantive defects (subtitle-hit resume skip, audio_path restore, shutdown-preserved-recoverable, NULL-status 500, fake-pass cancel test); main session diagnosed TestClient/ASGITransport SSE deadlock (transport awaits full ASGI completion; httpx timeout ineffective) — tests use raw-ASGI consume helper. Approved freeze exception: per-user cookiefile wired into all yt-dlp stages. 281 tests passed.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `cdd1054` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: C5 frontend contract adaptation

**Date**: 2026-09-06
**Task**: C5 frontend contract adaptation
**Branch**: `refactor/rewrite-core-pipeline`

### Summary

Implemented C5: frontend switched to the new pipeline contract — TaskStatus/TaskPhase types, ProgressEvent SSE payload, phase-based StepIndicator with failedPhase highlighting, shared progress synthesis module (URL/upload paths), status-based terminal detection in useSSE, i18n rewrite (en/zh-CN) with new phase and error-code keys. 60/60 frontend tests green, build passes; check agent verified zero contract drift field-by-field. All 5 subtasks of the core-pipeline rewrite are now delivered (G1-G4 gates passed).

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `ca7e7ec` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: Parent task: live acceptance + integration fixes + wrap-up

**Date**: 2026-09-06
**Task**: Parent task: live acceptance + integration fixes + wrap-up
**Branch**: `refactor/rewrite-core-pipeline`

### Summary

Live acceptance of the rewritten pipeline against real Bilibili URLs surfaced and fixed 3 integration defects: (1) stage-level retry for transient CDN failures with real yt-dlp stderr surfaced and classified; (2) video_meta dict serialization + immediate update_task_meta (title/thumbnail were NULL during processing and lost even at completion); (3) SDK TranscriptionSegment attribute access (migrated code used dict subscripts). Final state: 290 backend + 60 frontend tests green, builds pass, end-to-end URL task produces timestamped Markdown notes (48 clickable links on acceptance video). All 5 subtasks + parent archived; spec updated with final pipeline status and lessons (dataclass artifacts, dict-vs-object SDK shapes, transport retry policy).

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `36b3997` | (see git log) |
| `27681a2` | (see git log) |
| `8f0074e` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 10: Redesign note detail page layout and interactions

**Date**: 2026-09-07
**Task**: Redesign note detail page layout and interactions
**Branch**: `emdash/wild-snakes-sneeze-uwuv8`

### Summary

Replaced the note detail page's fixed left sidebar with a sticky NoteDetailHeader (title, meta info, save status, compact actions) and a reading-focused centered body (max-w-3xl). Tags + folder management moved into a unified NoteMetaPopover (@base-ui Popover provides outside-click/Esc close). TOC docks on xl+ and collapses into a Sheet below xl. Processing failures now keep VideoInfoCard + retry via processError state instead of swapping to the bare error branch. Added 13 test cases (73 total green). Spec updated with shadcn popover install pitfalls and @base-ui jsdom testing patterns.

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `46dc337` | (see git log) |
| `32825ca` | (see git log) |
| `6788989` | (see git log) |
| `10795bb` | (see git log) |
| `3e07e7b` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete

## Session 11: Settings: preselect first provider preset in empty state

**Date**: 2026-09-07
**Task**: Settings: preselect first provider preset in empty state
**Branch**: `feat/settings-default-provider-preset`

### Summary

Researched BYOK provider-config UX patterns (LobeChat/Cherry Studio/Open WebUI/Warp); implemented first-preset preselection in SettingsPage buildConfigForm for unconfigured ASR/LLM (provider + api_base auto-filled, model left empty, saved-config echo unchanged). Added 4 unit tests, documented preset-order-as-recommended-default convention in frontend component guidelines, committed, checked, and archived task 09-07-default-provider-preset. Branch renamed to conventional feat/ naming; PR #51 created and conflict against main resolved (session journal renumbering).

### Main Changes

| Hash | Message |
|------|---------|
| `072706a` | (see git log) |

## Session 11: Fix meta backfill race in NewNotePage execution view

**Date**: 2026-09-07
**Task**: Fix task meta backfill race in NewNotePage execution view
**Branch**: `fix/meta-backfill-race`

### Summary

Diagnosed and fixed a frontend race in NewNotePage: the one-shot task-meta backfill fired on the first non-pending SSE progress, but the backend persists title/thumbnail (update_task_meta) only after the fetching stage completes, so the execution view showed no title/cover for the whole run. Fix: refetch fetchTaskById when the SSE phase advances past 'fetching' while title/thumbnail are still missing; upload tasks bail out; retry resets the fetch refs. Added 3 tests covering phase-advance refetch, no redundant refetch, and upload no-loop. tsc/eslint/vitest all green (76 tests).

### Git Commits

| Hash | Message |
|------|---------|
| `6cde916` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete
