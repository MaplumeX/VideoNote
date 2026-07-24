# Implement — Fix core pipeline logic bugs and UX issues

## Execution Plan

按依赖与风险从低到高排序,分 6 个阶段。每阶段结束运行相应测试作为 review gate。

### Phase A — 后端契约与类型(无行为变更,打地基)

- [ ] A1 `backend/app/schemas.py`:`ProcessResponse` / `UploadResponse` 增加 `source_type: Literal["url","upload"]` 字段。
- [ ] A2 `backend/app/errors.py`:新增 `PROVIDER_NOT_CONFIGURED` 错误码(若 errors.py 是字典/常量集合)。
- [ ] A3 `backend/app/api/routes.py`:
  - `process_video` 正常分支返回 `source_type="url"`,dedup 分支从 DB dict 读 `source_type` / `title` / `thumbnail_url` 一并返回。
  - `upload_video` 返回 `source_type="upload"`。
  - `retry_task` 两个分支分别返回 `source_type="url"` / `"upload"`。
- [ ] Gate:`cd backend && uv run pytest -q` 全过;`uv run ruff check .` 无新告警。

### Phase B — 主流程 helper 抽取(为后续修改铺路)

- [ ] B1 `routes.py` 新增 `ProviderBundle` dataclass 与 `_resolve_providers(user_id)` async 函数(读 user config + 回退环境变量)。
- [ ] B2 新增 `_StageFailed` 异常类与 `_make_asr_progress_cb` / `_make_note_progress_cb` 工厂。
- [ ] B3 新增 `_run_asr(job_id, audio_path, language, asr_cfg, cancel_event, progress_cb) -> str`(抛 `_StageFailed`)。
- [ ] B4 新增 `_run_note_gen(job_id, transcript, video_title, language, llm_cfg, cancel_event, progress_cb) -> str`(抛 `_StageFailed`)。
- [ ] B5 重写 `_process_video_url` / `_process_video_file` 调用上述 helper,删除重复段。保持外层 try/except 结构不变(失败仍写固定 code + message)。
- [ ] Gate:`uv run pytest -q test_core_reliability.py test_pipeline_bugs.py` 全过(行为等价回归)。

### Phase C — 错误透传 + Provider 前置校验(依赖 B)

- [ ] C1 `routes.py` 新增 `_sanitize_error_detail(exc) -> str`(剥离 `sk-...` / Bearer / cookie,截断 200 字符)。
- [ ] C2 `_StageFailed` 除 `code` 外携带 `detail`;helper 抛出时填入 sanitized detail;detail 为空时退化为空字符串。
- [ ] C3 外层 except 把 `message` 写为 `f"{code}: {detail}"`(detail 为空时退化为纯 `code`),不扩 DB schema,detail 直接拼进 `message` 文本列。
- [ ] C4 前端 `translateTaskMessage` 配套改为前缀匹配(取首个 `: ` 前为 code,后为 detail),无 `: ` 时回退原等值匹配。此项实际在 Phase F 完成,后端先合不破坏。
- [ ] C5 新增 `_ensure_providers_configured(user_id) -> str | None`,在 `/process` / `/upload` / `/retry` 调度前调用,返回 `PROVIDER_NOT_CONFIGURED` 时 raise HTTPException(422)。
- [ ] Gate:`uv run pytest -q`,新增 `test_error_detail_sanitization` / `test_provider_not_configured` 通过。

### Phase D — ASR 语言 + 取消响应 + 字幕去重(服务层)

- [ ] D1 `routes.py`:`_asr_language` 改为查表,返回 `str | None`。
- [ ] D2 `backend/app/services/transcribe.py`:`transcribe_audio` / `_transcribe_file` 接受 `language: str | None`,`None` 时不传 `language` 给 OpenAI。
- [ ] D3 `backend/app/services/subtitle.py`:
  - `get_video_info_strict` 调用前后增加 `cancel_event.is_set()` 检查。
  - `extract_subtitles` 重构为单次 `download([url])` 路径,删除先 `extract_info(download=False)` 探测的分支;download 后按 `languages` 顺序选首个 `.srt`/`.vtt`。
- [ ] Gate:`uv run pytest -q test_subtitle_ytdlp_opts.py test_pipeline_bugs.py`,新增 `test_asr_language_mapping` 通过。

### Phase E — retry upload 拷贝 + safe_name 加固(routes 层)

- [ ] E1 `routes.py`:`retry_task` upload 分支 `shutil.copy2` 旧 input file 到新 job_id 文件,新任务 `input_file_path` 指向拷贝。
- [ ] E2 `routes.py`:`upload_video` 用 `_sanitize_upload_name(filename)` 替换原 `safe_name` 逻辑。
- [ ] Gate:新增 `test_retry_upload_copies_file` / `test_sanitize_upload_name` 通过;现有测试不回归。

### Phase F — 前端 SSE、retry、upload、provider error、i18n

- [ ] F1 `frontend/src/types/index.ts`:`TaskProgress` 增加 `title?: string | null` / `thumbnail_url?: string | null` / `detail?: string | null`。
- [ ] F2 `frontend/src/api/client.ts`:
  - `translateTaskMessage` 改为前缀匹配:若 message 含 `:`,前缀作为 code 查 i18n,后缀作为 detail 追加。
  - `submitUrl` / `retryTask` / `upload` 返回类型增加 `source_type`;新增 `PROVIDER_NOT_CONFIGURED` 的 i18n key 映射。
- [ ] F3 `frontend/src/hooks/useSSE.ts`:
  - 收到首个 `progress`/`complete` 事件后 `reconnectAttempt = 0`。
  - `fetchTaskById` 恢复后若 stage 仍 processing,`reconnectAttempt = 0` 后继续重连(不 `++`)。
- [ ] F4 `frontend/src/hooks/useVideoUpload.ts`:401 分支 `silentRefresh()` 成功后用新 token 自动重发(闭包 `attemptedRefresh` 标志防循环)。
- [ ] F5 `frontend/src/pages/NewNotePage.tsx`:
  - `handleRetry` 用 `data.source_type` 替换硬编码 `"url"`。
  - `handleUrlSubmit` / `handleFileUpload` 用 `data.source_type`。
  - 监听 `progress?.title` / `progress?.thumbnail_url` 更新 `taskMeta`。
  - 错误展示若含 `PROVIDER_NOT_CONFIGURED`,引导去设置页(按钮跳转 `/app/settings`)。
- [ ] F6 `frontend/src/i18n/index.ts`:新增 `errors.PROVIDER_NOT_CONFIGURED`、`errors.uploadSessionExpired` 等缺失 key(en + zh-CN)。
- [ ] Gate:`cd frontend && npm run lint && npm run build && npm test` 全过;新增 `useSSE.test.ts` 覆盖重连归零场景。

### Phase G — 终检

- [ ] G1 后端全测:`cd backend && uv run pytest -q`。
- [ ] G2 前端全测:`cd frontend && npm test -- --run`。
- [ ] G3 ruff:`cd backend && uv run ruff check .`。
- [ ] G4 手测清单(可选,记录到 journal):
  - 提交 YouTube URL,观察 NewNotePage 信息卡在 `update_task_meta` 后立即显示。
  - 上传视频时手动使 token 过期,观察自动重发。
  - 长视频(>30 min 处理)SSE 不断连。

## Validation Commands

```bash
# Backend
cd backend && uv run pytest -q && uv run ruff check .

# Frontend
cd frontend && npm run lint && npm run build && npm test -- --run
```

## Review Gates

- Phase B 后:helper 抽取不回归(运行 `test_core_reliability` / `test_pipeline_bugs`)。
- Phase C 后:错误透传与 provider 校验单测通过。
- Phase D 后:ASR 语言映射 + 字幕去重单测通过,`test_subtitle_ytdlp_opts` 不回归。
- Phase E 后:retry upload 与 safe_name 单测通过。
- Phase F 后:前端 SSE / upload / retry 单测与构建通过。
- Phase G:全量测试 + lint。

## Rollback Points

- 每个 Phase 完成后即可作为一个 rollback 点(单独 commit)。
- 若 Phase B helper 抽取引发回归且无法快速修复,可单独回滚 Phase B,保留 Phase A 的契约扩展(向后兼容)。
- Phase C 的 message 格式变更与前端 F2 必须同 PR;若前端未就绪,后端不要先合(会破坏 `translateTaskMessage` 等值匹配)。
  - **缓解**:Phase C 后端先用新格式 `f"{code}: {detail}"` 但 detail 为空时退化为纯 `code`,前端 `translateTaskMessage` 改为前缀匹配后对纯 `code` 也兼容。这样后端可先合,前端跟进。