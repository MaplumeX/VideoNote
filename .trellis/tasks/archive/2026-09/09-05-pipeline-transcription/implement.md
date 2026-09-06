# 执行计划：C2 转录子流水线重写

## Checklist（有序）

### Part A：子进程托管
- [ ] A1 `pipeline/subprocess_util.py`：`run_managed_process`（取消 terminate→kill、timeout、CancelledError 不泄漏进程）+ `build_ytdlp_args`（cookie/proxy/print-json 集中构建，含 `YT_DLP_COOKIES_FROM_BROWSER` 语法解析迁移）+ `classify_ytdlp_error(text) -> ErrorCode` 纯函数（spec error-handling 关键词表逐条迁移）

### Part B：四个阶段模块
- [ ] B1 `pipeline/stages/fetch.py`：yt-dlp CLI 元信息 + httpx 异步缩略图（非致命）→ `video_meta` 产物
- [ ] B2 `pipeline/stages/subtitle.py`：字幕下载 + `parse_srt_or_vtt` 纯函数（迁移 `_srt_to_transcript` 全语义）→ `subtitle` 产物或空 outputs（未命中）
- [ ] B3 `pipeline/stages/audio.py`：yt-dlp 下载 + ffmpeg WAV 转码（文件源仅 ffmpeg）→ `audio_path` 经 `StageResult.extra` 传递
- [ ] B4 `pipeline/stages/transcribe.py`：Async[OI] ASR、切块拼接（`_shift_timestamps` 迁移）、逐块进度、SiliconFlow 分支 → `transcript` 产物
- [ ] B5 `stages/base.py` 最小扩展：`StageResult.extra` 字段（已向父任务备案，见 design.md §9）

### Part C：测试
- [ ] C1-1 `test_subprocess_util.py`（真实 sleep 子进程取消 ≤3s、timeout、无泄漏）
- [ ] C1-2 `test_stage_fetch.py`（stub yt-dlp 脚本 + 错误分类矩阵 + 缩略图非致命）
- [ ] C1-3 `test_stage_subtitle.py`（SRT/VTT fixtures + 未命中语义）
- [ ] C1-4 `test_stage_audio.py`（真实 ffmpeg + 1s 正弦波 fixture）
- [ ] C1-5 `test_stage_transcribe.py`（fake Async[OI]：单块/多块/取消/SiliconFlow）

## 验证命令

```bash
cd backend
uv run ruff check app/ tests/
uv run python -m pytest tests/ -q
which ffmpeg ffprobe   # 环境前置确认
```

## 边界与禁止事项

- **禁止修改**：`app/services/**`、`app/api/routes.py`、`app/task_runner.py`、`pipeline/state.py`/`errors.py`/`progress.py`（C1 冻结契约；唯一允许改动是 `stages/base.py` 增加 `StageResult.extra` 字段）。
- 禁止 `threading.Event`、禁止 `asyncio.to_thread` 包同步 yt-dlp/ffmpeg 调用（全部子进程或异步客户端）。
- 禁止 shell=True（列表参数 exec）。

## 风险与回滚

- yt-dlp CLI 输出/行为与 Python API 差异 → stub 脚本测试 + 参数构建集中一处；C4 集成时再用真实 URL 冒烟。
- `StageResult.extra` 属契约补充 → 同步更新 docs/pipeline-contract.md（StageResult 节），保持文档与代码零漂移。

## 完成定义

- checklist 全完成，ruff + 全量 pytest 绿（含 C1 与旧链路测试）
- 取消测试证明：子进程在取消后 ≤3s 终止且无残留进程
