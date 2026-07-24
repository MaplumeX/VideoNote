# Design — Fix core pipeline logic bugs and UX issues

## Scope & Boundaries

本任务跨前后端,但所有改动都在"核心链路"边界内:

- 后端:`backend/app/api/routes.py`、`backend/app/services/{subtitle,transcribe,note_gen,audio}.py`、`backend/app/{schemas,errors,db}.py`、`backend/app/task_runner.py`
- 前端:`frontend/src/hooks/{useSSE,useVideoUpload}.ts`、`frontend/src/pages/{NewNotePage,NoteDetailPage}.tsx`、`frontend/src/components/{StepIndicator,VideoInfoCard}.tsx`、`frontend/src/api/client.ts`、`frontend/src/types/index.ts`、i18n 资源
- 不涉及:DB schema 变更(复用现有列)、authtable 变更、部署/镜像配置

## Contracts & Data Flow

### C1 视频信息可见(遵循 spec:不扩展 SSE)

> **Spec 对齐**:`.trellis/spec/guides/cross-layer-thinking-guide.md` 明确 "Don't extend SSE for static metadata that doesn't change during processing",建议 initiating page 用 POST 响应(Approach C)、observer page 用 `fetchTaskById`(Approach B)。因此**不扩展 SSE progress 事件 schema**,改用已有 REST 接口拉取 title/thumbnail。

SSE 端点 `GET /api/tasks/{job_id}/progress` 保持原样(progress 事件只携带 `stage/progress/message`)。

信息可见的实现:
- **dedup 分支**(Approach C):`process_video` dedup 分支从 DB dict 读 `title` / `thumbnail_url` / `source_type` 一并在 POST 响应返回。NewNotePage 拿到后直接填 `taskMeta`。
- **新提交分支**(Approach B):NewNotePage 在 SSE 首个 progress 事件(stage 变化)时调用 `fetchTaskById(jobId)` 拉取 task 元数据(title/thumbnail)。由于 `update_task_meta` 在 `extracting_subtitles` progress 写入之前已完成,DB 中 title 已就绪。若首拉仍为空(stage 还在 pending),在下次 stage 变化时再拉一次。
- `complete` 事件不变。
- 前端 `TaskProgress` 类型不新增 title/thumbnail 字段;由独立 `fetchTaskById` 调用获取。

### C2 ProcessResponse 契约(增 source_type)

`ProcessResponse` / `UploadResponse` 增加 `source_type: Literal["url","upload"]` 字段。
- `process_video`(URL)返回 `source_type="url"`。
- `retry_task` 的 URL 分支返回 `source_type="url"`,upload 分支返回 `source_type="upload"`。
- `upload_video` 返回 `source_type="upload"`。
- dedup 分支返回 DB 中已有任务的 `source_type` 与 `title` / `thumbnail_url`(若有)。

前端 `submitUrl` / `retryTask` / `upload` 全部读 `data.source_type`,删除 NewNotePage 中对 `taskMeta?.source_type === "upload"` 之外来源的硬编码推断。retry 不再写死 `"url"`。

### C3 错误信息透传契约

失败分支写 `message` 时改为 `f"{CODE}: {detail}"`,其中 `detail` 是去敏感后的异常摘要:
- 移除子串中的 api_key(正则 `sk-[A-Za-z0-9-_]{8,}` / Bearer 头)、完整 cookie 内容。
- 保留 HTTP 状态码、provider 错误体片段(截断 200 字符)、模型名。
- `detail` 为空时退化为纯 `CODE`,保证向后兼容。
- 前端 `translateTaskMessage(message)` 改为前缀匹配:取首个 `: ` 之前的部分作为 code 查 i18n,后缀作为 detail 追加展示;无 `: ` 时回退原等值匹配。
- **不扩 DB schema**:detail 直接拼进 `message` 字段(文本列,容量充足),SSE 端点轮询 DB 拿到的就是完整字符串。

错误码命名保持稳定(只丰富 detail)。新增唯一 code:`PROVIDER_NOT_CONFIGURED`。

### C4 Provider 前置校验

新增 `_ensure_providers_configured(user_id) -> str | None`,在 `/process`、`/upload`、`/retry` 调度前调用:
- 返回 `"PROVIDER_NOT_CONFIGURED"` 当 ASR 或 LLM 的最终 `api_key` 为空(环境变量与用户配置都未提供)。
- `/process` / `/upload` 在调度前 raise HTTPException(422, PROVIDER_NOT_CONFIGURED)。
- `/retry` 在调度前同样校验(因为新任务才需要 provider)。

### C5 ASR 语言映射

`_asr_language(note_lang)` 改为查表:

```python
_ASR_LANG_MAP = {"zh-CN": "zh", "en": "en", "ja": "ja"}
def _asr_language(note_lang: str) -> str | None:
    return _ASR_LANG_MAP.get(note_lang)  # None 表示不传 language,让 Whisper 自动探测
```

`transcribe_audio` / `_transcribe_file` 接受 `language: str | None`,`None` 时不传 `language` 参数给 OpenAI(Whisper 自动探测)。SiliconFlow 分支保持原行为(它本来就不传 language)。

### C6 SSE 重连配额修复

`useSSE.ts` 改动:
- 引入 `firstEventReceived` 局部标志。
- 收到首个 `progress` 或 `complete` 事件后,`reconnectAttempt = 0`。
- `fetchTaskById` 恢复后若 `task.stage` 仍在 processing,同样视为"恢复成功",`reconnectAttempt = 0`,然后继续外层 while 重连(不再 `++`)。
- 网络抖动(建连即抛 / 未收到任何事件就断)仍按指数退避 `++`,达 3 次后提示连接丢失。

### C7 上传 token 过期自动重发

`useVideoUpload.ts` 改动:
- `xhr.onload` 401 分支:`silentRefresh()` 成功后,用新 token 重新 `xhr.open` + `setRequestHeader` + `xhr.send` 同一 FormData。
- 用闭包内的 `attemptedRefresh` 标志防止无限循环(最多 refresh 一次)。
- refresh 失败仍按原行为提示。

### C8 取消响应性(extract_info 阶段)

在 `get_video_info_strict` 和 `extract_subtitles` 的 yt-dlp 调用前后增加显式 `cancel_event` 检查:
- 调用前 `if cancel_event is not None and cancel_event.is_set(): raise yt_dlp.utils.DownloadCancelled("Cancelled by user")`。
- 调用后(同步返回后)再检一次。
- 不引入轮询;主事件循环通过 `asyncio.to_thread` 调用,检查点在 thread 函数内。

### C9 字幕提取去重

`extract_subtitles` 重构为单次 `download([url])` 路径:
- 用 `writesubtitles` / `writeautomaticsub` + `subtitleslangs=languages` + `skip_download=True` 一次 download。
- 下载完成后在 tmpdir glob `.srt`/`.vtt`,按 `languages` 顺序选第一个匹配的(手动字幕优先,再自动)。
- 不再先 `extract_info(download=False)` 探测;若 download 后无字幕文件,返回 None。
- 保持 `cancel_event` hook 不变。

### C10 retry upload 文件拷贝

`retry_task` 的 upload 分支:
- `shutil.copy2(src, dst)` 把旧 input file 拷贝为新 job_id 命名的文件,新任务 `input_file_path` 指向拷贝。
- 新任务的 `_process_video_file` finally 只删自己的拷贝,不影响原 failed 任务的 `input_file_path`。
- 路径安全:拷贝目标仍在 `UPLOAD_DIR` 下,文件名 `{new_job_id}_{safe_name}`。

### C11 主流程去重(helper 抽取)

在 `routes.py` 新增:

```python
async def _resolve_providers(user_id: str | None) -> ProviderBundle:
    """返回 (asr_cfg, llm_cfg),所有字段回退到环境变量。"""

def _make_asr_progress_cb(job_id, loop, cancel_event, base, span):
    """返回 (fraction, msg) -> None 的回调,内部 run_coroutine_threadsafe。"""

async def _run_asr(job_id, audio_path, language, asr_cfg, cancel_event, progress_cb) -> str | None:
    """包装 transcribe_audio 调用 + 异常分类。失败时 raise _StageFailed(stage, code, detail)。"""

async def _run_note_gen(job_id, transcript, video_title, language, llm_cfg, cancel_event, progress_cb) -> str | None:
    """包装 generate_notes 调用 + 异常分类。"""
```

`_process_video_url` / `_process_video_file` 改为:
1. `_cancellation_checkpoint`
2. `_resolve_providers`
3. 各自获取 transcript 的差异部分
4. 共用 `_run_asr` + `_run_note_gen`
5. 异常由 helper 统一抛 `_StageFailed`,外层 try 统一写 `failed`/`cancelled`。

辅助类型:

```python
@dataclass
class _StageFailed(Exception):
    code: str
    detail: str
    cancelled: bool = False
```

### C12 upload safe_name 加固

```python
import re
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\u4e00-\u9fff-]")  # 保留字母数字 . _ - 与 CJK
def _sanitize_upload_name(filename: str | None) -> str:
    base = Path(filename).name if filename else "upload"
    base = _SAFE_NAME_RE.sub("_", base)
    base = base.replace("..", "_").strip(". ") or "upload"
    return base
```

最终路径仍由 `UPLOAD_DIR / f"{job_id}_{safe_name}"` 拼接,`job_id` 是 uuid,无路径越界风险。

## Tradeoffs & Compatibility

- **C1 SSE 字段扩展**:progress 事件增字段对旧前端是向后兼容的(多出的字段被忽略);对旧后端,新前端 `progress?.title ?? null` 同样安全。无版本耦合风险。
- **C2 ProcessResponse 增字段**:FastAPI `response_model` 会序列化新字段,旧前端忽略;新前端读新字段。无破坏。
- **C3 错误透传**:message 格式从 `CODE` 变为 `CODE: detail`(detail 为空时退化为纯 `CODE`)。前端 `translateTaskMessage` 改为前缀匹配以兼容两种形式。
  - **兼容策略**:后端可先合(detail 为空时与旧格式无异),前端 `translateTaskMessage` 改为前缀匹配后对纯 `CODE` 也兼容。同 PR 合入最佳,但不会因先后顺序造成 UI 破坏。
- **C5 language=None**:OpenAI SDK 的 `audio.transcriptions.create` 不传 `language` 是合法的(自动探测)。SiliconFlow 分支已不传 language。
- **C9 字幕提取去重**:重构后不再先 `extract_info(download=False)` 探测。若视频无任何字幕,download 会在 tmpdir 产生空结果,返回 None。行为等价但延迟减半。
- **C11 helper 抽取**:改动面大,须保证现有 `test_core_reliability` / `test_pipeline_bugs` 不回归。采用"先抽 helper、保留旧函数签名、逐步替换"策略。

## Rollout / Rollback

- 单分支单 PR,测试通过后合并。
- 无 DB migration,无配置变更,无需灰度。
- 回滚即 revert 该 commit;无副作用残留(SSE 字段、ProcessResponse 字段对旧版本透明)。

## Test Strategy

- 单测:
  - `test_sse_reconnect_reset`:mock 后端 30 min 关闭 + 恢复,断言 `reconnectAttempt` 归零。
  - `test_asr_language_mapping`:`zh-CN → zh`、`en → en`、`ja → ja`、`fr → None`。
  - `test_error_detail_sanitization`:api_key 被剥离,detail 截断。
  - `test_provider_not_configured`:无 provider 时返回 422。
  - `test_sanitize_upload_name`:`..`、路径分隔符、空名。
  - `test_retry_upload_copies_file`:原 failed 的 input_file_path 仍可再次 retry。
- 集成/回归:
  - 现有 `test_core_reliability` / `test_pipeline_bugs` 全部通过。
  - `test_subtitle_ytdlp_opts` 不回归。
- 手测(可选):
  - 提交一个 YouTube URL,观察 NewNotePage 信息卡在 `update_task_meta` 后立即显示标题/封面。
  - 上传视频时手动使 access token 过期,观察自动重发。