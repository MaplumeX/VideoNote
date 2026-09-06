# 重写核心流水线：转录 + LLM 笔记生成（父任务）

## Goal

完全重写 VideoNote 后端核心流水线（视频 → 字幕/ASR 转录 → LLM 笔记生成），通过架构升级根治 bug 频发的问题：阶段状态机 + 中间产物持久化、真正的取消语义、阶段驱动的两级进度模型。允许破坏性变更（API 契约、SSE 事件格式、DB schema）。前端契约适配纳入本任务树。

本任务为父任务：持有总需求、跨子任务验收标准、契约评审与最终集成验收；实际实现工作由 5 个子任务承担。

## Background

### 现有架构（代码证据）

- 编排逻辑内联在 `backend/app/api/routes.py`（1250 行）：`_process_video_url` / `_process_video_file` 两个巨型协程，串联字幕提取 → 音频下载 → ASR → LLM 笔记生成。
- 各阶段是同步阻塞函数，通过 `asyncio.to_thread` / `_to_thread_with_cancel`（`routes.py:101`，轮询 `threading.Event`，3s 周期）调用：
  - `services/subtitle.py`（303 行）：yt-dlp 字幕提取 + SRT/VTT 解析（`_srt_to_transcript`）。
  - `services/audio.py`（110 行）：yt-dlp 音频下载（`download_audio_via_ytdlp`）+ ffmpeg WAV 提取（`extract_audio`）。
  - `services/transcribe.py`（218 行）：同步 [OI] Whisper / SiliconFlow ASR，大文件按大小切块 + `_shift_timestamps` 拼接。
  - `services/note_gen.py`（380 行）：同步 LLM 笔记生成，`_split_transcript`（60k 字符）分块 + `_merge_notes` 合并 + `finish_reason == "length"` 续写。
- `task_runner.py`（89 行）：单进程 asyncio 任务注册表 + `threading.Event` 取消。
- 进度：手工固定区间（ASR 映射 [0.30, 0.60] 或 [0.20, 0.60]，见 `routes.py:520,611`），`update_progress` 写 SQLite（tasks 表 stage/progress/message 列）。
- SSE：`GET /tasks/{job_id}/progress`（`routes.py:827`），1s 轮询 DB + 15s 心跳，`progress` 事件载荷 `{stage, progress, message}`，终态附加 `complete` 事件。

### 历史问题（archive/2026-07 ~ 2026-09 至少 6 轮集中修复）

1. **同步/异步边界缺陷**：`_to_thread_with_cancel` 只能放弃等待，线程继续跑完（取消不深入阻塞调用）；`process_ie_result` 返回值误用为 retcode（P0，`audio.py`）。
2. **错误处理分散**：`_StageFailed` + `_sanitize_error_detail` + 错误码字符串散落各层。
3. **进度语义脆弱**：手工区间在有无字幕分支间回退/跳变，多次返工。
4. **资源与一致性**：临时文件清理、恢复无上限、重复提交去重问题反复出现。
5. **测试薄弱**：74 个测试大多依赖 mock，bug 存在于 mock 掩盖或无覆盖路径。

### 前端契约依赖面

- `frontend/src/types/index.ts`：`TaskStage` 枚举、`TaskProgress {stage, progress, message}`。
- `frontend/src/hooks/useSSE.ts`（196 行）、`components/StepIndicator.tsx` / `StatusBadge.tsx` / `ProgressBar.tsx`、`pages/NewNotePage.tsx` 进度展示。

## Confirmed Decisions

- **D1 重写深度**：架构升级式重写——阶段状态机 + 中间产物持久化（可从任意阶段恢复/重试）；yt-dlp/ffmpeg 子进程托管可 kill + ASR/LLM 异步 [OI] 客户端（真取消）；「阶段 + 阶段内进度」两级模型。
- **D2 前端范围**：纳入任务树，作为最后一个子任务（C5）；后端先稳定契约并产出契约文档，前端据此适配；范围限于 types/useSSE/进度 UI，不涉及编辑器与笔记管理。
- **D3 拆分形态**：父任务 + 5 个子任务，依赖顺序 C1 → (C2 ∥ C3) → C4 → C5；依赖写入各子任务 prd.md，不靠树形位置暗示。父任务不做直接实现，除非集成修复。

## Requirements（跨子任务）

- **R1 端到端功能保持**：提交 URL（YouTube/Bilibili）或上传文件 → 字幕优先、无字幕回退 ASR → LLM 生成带时间戳的 Markdown 笔记 → SSE 实时进度 → 结果持久化可管理。功能语义与现版对齐，实现与契约全新。
- **R2 阶段可恢复**：字幕文本、转录文本等中间产物落库；任务失败/重启后可从最后成功的检查点恢复，不重复消耗已完成的 ASR/LLM 费用；恢复有最大尝试次数上限。
- **R3 真取消**：取消请求在秒级终止底层 yt-dlp/ffmpeg 子进程与异步 ASR/LLM 请求；取消后无残留计费调用。
- **R4 两级进度**：进度模型为「阶段枚举 + 阶段内 fraction」，前端可独立于全局百分比渲染步骤状态；全程单调，无回退跳变。
- **R5 统一错误体系**：稳定错误码集中定义、一处脱敏，SSE/API 返回结构化错误（码 + 可读消息），不再拼字符串。
- **R6 可测试性**：新流水线各阶段为纯函数/可注入客户端，提供不依赖网络的真实路径测试（子进程用小 fixture，LLM/ASR 用假客户端），关键分支不被 mock 掩盖。

## 子任务地图

| # | 目录 | 交付物 | 依赖 |
|---|------|--------|------|
| C1 | `09-05-pipeline-state-machine` | DB schema 迁移、统一错误码、两级进度模型、契约文档 | 无 |
| C2 | `09-05-pipeline-transcription` | 子进程托管 yt-dlp/ffmpeg、异步 ASR、字幕解析重写 | C1 |
| C3 | `09-05-pipeline-notegen` | 异步 LLM、分块/合并/续写、逐 chunk 取消 | C1 |
| C4 | `09-05-pipeline-orchestrator` | 状态机编排器、检查点恢复、REST/SSE 新契约、routes.py 瘦身 | C2、C3 |
| C5 | `09-05-pipeline-frontend-adapt` | types/useSSE/进度 UI 适配新契约 | C4 |

## Acceptance Criteria（父任务集成验收）

- [ ] 端到端：有字幕视频 URL、无字幕视频 URL、本地上传文件三条路径均产出结构化 Markdown 笔记，时间戳链接可点击。
- [ ] 取消：任一阶段（字幕提取/音频下载/ASR/LLM 生成中）发起取消，≤3s 内任务进入 cancelled，子进程已终止、无后续 API 调用。
- [ ] 恢复：在 LLM 生成阶段人为失败后重试，不重跑转录（中间产物复用），attempt 上限生效。
- [ ] 进度：SSE 全程阶段单调推进，阶段内 fraction ∈ [0,1]，无回退；前端步骤指示器与后端阶段一一对应。
- [ ] 重启恢复：进程重启后未完成任务从检查点恢复或明确标记，不无限重试。
- [ ] 旧测试迁移：被重写模块的既有测试删除或迁移到新结构，测试套件全绿；新增路径有非 mock 测试覆盖。
- [ ] 现有非流水线功能（笔记管理、标签、文件夹、认证、Provider/Cookie 配置）回归无损。

## Out of Scope

- 多进程/多 Worker 任务队列（保持单进程 + SQLite 部署形态）。
- 新增 ASR/LLM Provider 类型（保持 [OI] 兼容端点 + SiliconFlow ASR）。
- Milkdown 编辑器、笔记管理 UI 的改动。
- 视频平台扩展（仍 YouTube/Bilibili）。

## Notes

- 父任务正常不做直接实现；若集成验收发现跨子任务缺陷，以父任务名义做集成修复。
- 各子任务 `task.py start` 前需完成各自规划文档与 implement.jsonl/check.jsonl 策展。
