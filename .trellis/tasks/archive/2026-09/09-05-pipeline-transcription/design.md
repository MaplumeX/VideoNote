# 技术设计：C2 转录子流水线重写

> 依赖 C1 冻结契约（`docs/pipeline-contract.md`、`app/pipeline/stages/base.py`）。本设计不改变契约，只实现它。

## 1. 模块布局（本任务产出）

```
backend/app/pipeline/
├── subprocess_util.py      # 子进程托管：asyncio.create_subprocess_exec 封装，取消即 kill
└── stages/
    ├── fetch.py            # FetchStage: yt-dlp CLI 取元信息 + 缩略图下载（httpx 异步）
    ├── subtitle.py         # SubtitleStage: yt-dlp CLI 下载字幕 + 纯函数解析
    ├── audio.py            # AudioStage: yt-dlp CLI 下载音频 + ffmpeg 转 WAV
    └── transcribe.py       # TranscribeStage: Async[OI] ASR + 大文件切块
```

旧 `app/services/{subtitle,audio,transcribe}.py` 不动（C4 切换后删除）。

## 2. subprocess_util.py 设计

```python
async def run_managed_process(
    args: list[str], *,
    cancel: CancelHandleRegistrar,     # 注册到编排器
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> ProcessResult:                    # returncode, stdout, stderr
```

- 基于 `asyncio.create_subprocess_exec`（列表参数，无 shell，天然防注入）。
- 取消联动：注册 cancel handle = `proc.terminate()`；若 5s 未退再 `proc.kill()`。
- `asyncio.CancelledError` 捕获后先 terminate/kill 再 re-raise，保证进程不泄漏。
- timeout 到期同样 terminate→kill，抛 `PipelineError(PROCESSING_FAILED, detail=...)`。
- 封装 yt-dlp 通用参数构建 `build_ytdlp_args(...)`：`--print-json`/`--dump-json`、cookie 文件、proxy、输出模板——集中一处，等价替代旧 `_ydl_opts`（proxy/cookie 语义全部保留，含 `YT_DLP_COOKIES_FROM_BROWSER` 语法解析的迁移）。

## 3. stages/fetch.py — FetchStage（phase=fetching）

- `yt-dlp --dump-json --no-download <url>` 取 `title`/`thumbnail`。
- 错误分类：复用旧 `classify_ytdlp_error` 的关键词映射（迁移为新模块内纯函数 `classify_ytdlp_error(text) -> ErrorCode`，规则表从 spec error-handling.md 逐条迁移），stderr 文本喂分类器，抛 `PipelineError(code)`。
- 缩略图：httpx 异步下载（Bilibili Referer 反防盗链语义保留），失败非致命（`thumbnail=None`，warning 日志）。
- 产出：`StageResult(outputs={ArtifactKind.video_meta: VideoMeta(title, thumbnail_filename)})`。
- 注：缩略图落盘到 UPLOAD_DIR/thumbnails（复用旧逻辑语义）；C4 编排器负责把 title/thumbnail 写入 tasks 行。

## 4. stages/subtitle.py — SubtitleStage（phase=subtitle）

- `yt-dlp --write-subs --write-auto-subs --sub-format srt --convert-subs srt --skip-download -o <tmpdir>/%(id)s <url>`。
- 语言优先级按 note language 重排（迁移 `_subtitle_languages` 语义）。
- 解析：`parse_srt_or_vtt(raw: str) -> str | None` 纯函数（迁移 `_srt_to_transcript`，保留 VTT NOTE/WEBVTT 头跳过、时间戳行定位、`[HH:MM:SS](#t=SECONDS)` 输出格式、空文本 cue 丢弃、无 cue 返回 None 语义）。
- 命中字幕：`outputs={subtitle: transcript_text}`；未命中：返回**空 outputs**（编排器据转移表走 audio→transcribe 分支，StageResult 无需表达分支决策——决策在产物层面自然发生）。
- yt-dlp 下载失败（非「无字幕」）：抛 `PipelineError(SUBTITLE_EXTRACTION_FAILED)`。区分方式：retcode!=0 或 stderr 含下载错误 → 失败；retcode==0 且无字幕文件 → 未命中。

## 5. stages/audio.py — AudioStage（phase=audio）

- URL 源：`yt-dlp -f bestaudio/best -o <tmpdir>/audio <url>`，成功后 ffmpeg 转 WAV（pcm_s16le/16kHz/mono——ASR 通用格式）。
- 文件源：ctx 携带输入文件路径（见 §9 接口扩展），仅 ffmpeg 转换。
- ffmpeg 参数沿用旧 `extract_audio`；ffprobe（chunk 时长探测）也走子进程。
- 临时文件：`tempfile.TemporaryDirectory` + try/finally，取消/异常路径不泄漏。
- 产出：音频路径不落 artifact（大文件不进 DB），StageResult 用 `outputs={transcript 前置}`——即 AudioStage 只负责产出 `audio_path`，通过 `StageResult.extra`（见 §9）传给编排器/下一阶段。

## 6. stages/transcribe.py — TranscribeStage（phase=transcribe）

- Async[OI] 客户端（`AsyncOpenAI`），构造自 `ctx.provider.asr`。
- 单文件 ≤ 上限（OpenAI 25MB / SiliconFlow 50MB）：直接转录。
- 超限：ffprobe 探时长 → ffmpeg 切块（chunk 时长计算迁移旧逻辑）→ 逐块 await 转录 → `_shift_timestamps` 偏移拼接（纯函数迁移）→ 逐块发布进度 `(i+1)/n`。
- 每块 await 前无需手动检查取消——`asyncio` 取消会直接中断 await 中的 HTTP 请求（这是异步化的核心收益）；块间用 `await asyncio.sleep(0)` 让出并不需要。
- 输出格式迁移：verbose_json segments → `[HH:MM:SS](#t=S) text` 行；SiliconFlow 纯文本分支保留。
- 语言映射迁移：`_asr_language`（zh-CN→zh, en→en, ja→ja，未映射→None 自动检测）。
- 错误：非可重试 ASR 错误抛 `PipelineError(TRANSCRIPTION_FAILED)`；网络类错误由 SDK 超时抛出后包装（不做应用层重试——重试策略统一在 C3 的 LLM 客户端做，ASR 保持简单；如需重试由 C4 编排器统一决定）。
- 产出：`outputs={transcript: text}`。

## 7. 取消语义（全阶段统一）

- 子进程：`run_managed_process` 内部注册 cancel handle（terminate→kill）。
- Async[OI]：无需句柄，asyncio 取消天然传播；StageContext.register_cancel 传 None 即可。
- 每个阶段入口若 `resume=True` 且已有本阶段产物 → 直接返回（幂等重入）。

## 8. 测试设计（tests/pipeline/）

- `test_subprocess_util.py`：真实子进程（`sleep`）验证取消 ≤3s 终止、timeout、stderr 捕获、CancelledError 后进程不存活。
- `test_stage_fetch.py`：fake yt-dlp（测试用 stub 脚本替代二进制，输出 fixture JSON）——参数构建断言（cookie/proxy/print-json）、错误分类（私享/地域/404/cookie/兜底各一例）、缩略图失败非致命。
- `test_stage_subtitle.py`：SRT/VTT fixtures（正常/NOTE头/无cue/空文本cue）、语言优先级、未命中=空 outputs、下载失败=SUBTITLE_EXTRACTION_FAILED。
- `test_stage_audio.py`：真实 ffmpeg + 小音频 fixture（生成 1s 正弦波 wav）验证转码参数与输出；URL 下载分支用 stub 脚本。
- `test_stage_transcribe.py`：注入 fake AsyncOpenAI——单块/多块拼接（时间戳偏移断言）/SiliconFlow 纯文本/取消中途抛 CancelledError/不可重试错误包装。
- 环境注意：ffmpeg/ffprobe 在 CI 必须可用（Dockerfile 已含；本地开发已验证存在）。

## 9. 契约内的最小扩展（需向父任务备案，不改语义）

`StageResult` 增加 `extra: dict[str, object]`（默认空）用于阶段间传递不适合落库的临时数据（如 audio_path）。这是实现层面发现的需求：audio→transcribe 之间必须传递本地文件路径，但音频文件不应作为 artifact 落库。对 `StageResult` 的扩展属于非破坏性补充，C1 冻结的核心枚举/错误码/进度模型不受影响。
