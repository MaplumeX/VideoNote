# 子任务 C2：转录子流水线重写

## Goal

重写转录侧阶段模块：yt-dlp / ffmpeg 全部改为可 kill 的子进程托管，ASR 改用异步 [OI] 客户端，字幕提取与 SRT/VTT 解析重写为纯函数，取消即时生效。

## Dependencies

- 依赖 C1（09-05-pipeline-state-machine）：使用其 state/errors/progress 契约与 StageContext/StageResult 接口。
- 可与 C3（pipeline-notegen）并行。
- 被 C4（pipeline-orchestrator）消费。

## Scope

- `pipeline/subprocess_util.py`：子进程托管（spawn/wait/kill，与 asyncio 取消联动）。
- `pipeline/stages/fetch.py`：视频元信息 + 缩略图（yt-dlp CLI 子进程，替代 `get_video_info_strict` Python API）。
- `pipeline/stages/subtitle.py`：字幕提取（yt-dlp CLI `--write-subs --skip-download`）+ SRT/VTT 解析纯函数（迁移 `_srt_to_transcript` 语义，保留语言优先级与时间戳格式）。
- `pipeline/stages/audio.py`：音频下载/提取（yt-dlp CLI + ffmpeg 子进程，替代 `download_audio_via_ytdlp` / `extract_audio`）。
- `pipeline/stages/transcribe.py`：Async[OI] ASR 客户端、大文件切块 + 时间戳偏移拼接（迁移 `transcribe.py` 语义，SiliconFlow 分支保留）。
- 错误分类迁移：`classify_ytdlp_error` 语义映射到 C1 错误码。

## Acceptance Criteria

- [ ] 所有 stage 模块签名 `async def run(ctx: StageContext) -> StageResult`，无 threading.Event。
- [ ] 取消：yt-dlp/ffmpeg 子进程在取消后 ≤3s 被终止（用长任务 fixture 实测，非 mock）。
- [ ] ASR：假客户端测试分块/拼接/取消；真实端点冒烟可选。
- [ ] 字幕解析：SRT/VTT fixture（含 VTT NOTE 头、无字幕回退 None 语义）测试通过。
- [ ] 历史 bug 不回归：`process_ie_result` 误用类缺陷在新结构中结构性不可再现（无该调用路径）。

## Notes

- yt-dlp CLI 与 Python API 行为差异（cookie 文件、格式选择、JSON 输出）需 fixture 实测对比。
