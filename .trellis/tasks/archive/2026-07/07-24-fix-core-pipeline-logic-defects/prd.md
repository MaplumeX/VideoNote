# Fix core pipeline logic defects

## Goal

修复核心链路（ASR 转写 → 笔记生成 → 笔记编辑）中四个已确认的真实逻辑缺陷，使长视频时间戳准确、编辑后的标题在列表一致、长视频笔记不被截断或失败、并对进度状态机的隐含约束形成文档说明。

R-C 采用最小修复范围：放宽 `max_tokens` 并对超长 transcript 做截断保护，不做分章 map-reduce（后者作为独立后续任务）。

## Background — Confirmed Facts (代码证据)

### A. 大文件 ASR 分块时间戳偏移丢失（严重）
- 文件：`backend/app/services/transcribe.py :: _transcribe_large_file`
- `_transcribe_large_file` 用 `ffmpeg -ss {start} -t {chunk_duration}` 从原音频 `start` 秒处切块，但拼接时直接 `full_transcript_parts.append(_transcribe_file(...))`，**未把 `start` 偏移加回到每个 chunk 的段时间戳上**。
- `_transcribe_file` 返回 `[HH:MM:SS](#t={seg['start']})`，其中 `seg['start']` 是 Whisper 对该 chunk 文件**从 0 开始**的相对时间。
- 触发条件：音频 > 25MB（OpenAI）或 > 50MB（SiliconFlow），约对应 20~30 分钟以上视频。
- 后果：拼接后时间戳每块从 0 重新开始；下游 `has_timestamps = "#t=" in transcript` 为 True，走"保留时间戳" prompt，错误时间戳被原样保留进笔记，点击跳转完全错位。
- siliconflow 分支返回纯文本无时间戳，不受影响；仅 OpenAI verbose_json 分支受影响。

### B. 编辑笔记标题后列表仍显示旧标题
- 文件：`backend/app/db.py :: update_note_content`
- `update_note_content` 只写 `result_json.markdown/title`，**不更新 `tasks.title` 列**。
- `routes.py :: update_task_meta`（URL 任务）会把 `video_title` 写入 DB `title` 列（非空）。
- `get_user_tasks` / `get_single_task` 取 title 优先级：`task["title"]（DB列） or result_json.title`。
- 因此 URL 任务用户在编辑器改标题保存后，DB `title` 列仍是原始视频标题，列表/侧栏显示旧标题。

### C. 长视频笔记被截断或失败
- 文件：`backend/app/services/note_gen.py :: generate_notes`
- `max_tokens=4096` 硬编码，长视频结构化笔记会被截断，无续写/分章机制。
- 超长 transcript 整段塞入 messages，无 map-reduce 分块，可能超出模型上下文窗口 → `NOTE_GENERATION_FAILED`，整个任务失败。

### D. update_progress 终端态语义隐含约束（文档性）
- 文件：`backend/app/db.py :: update_progress`
- WHERE 条件 `stage NOT IN (complete, failed, cancelled)`：首次写 `failed` 成功，之后任何进度更新被静默丢弃。
- 当前 `_process_video_*` 在失败后即 return，未踩坑；但是隐含约束，建议在代码注释和/或 spec 中显式说明，避免后续误用（例如"失败后再写更细错误信息"会静默失败）。

## Requirements

### R-A ASR 分块时间戳偏移修正
- R-A.1 `_transcribe_large_file` 拼接每个 chunk 的转写结果前，把该 chunk 的起始偏移 `start` 秒加到每条 `[HH:MM:SS](#t=SECONDS)` 的时间戳上（包括显示时间 `HH:MM:SS` 与跳转秒数 `SECONDS`）。
- R-A.2 偏移逻辑须同时处理 OpenAI verbose_json 分支（带时间戳）；siliconflow 纯文本分支不产生 `#t=`，按现状拼接即可。
- R-A.3 修正后时间戳通过 `has_timestamps` 判定与下游 LLM prompt 一致保留。

### R-B 笔记标题编辑一致性
- R-B.1 `update_note_content` 在更新 `result_json` 的同时，同步更新 `tasks.title` 列（当传入 `title` 非空时）。
- R-B.2 编辑器保存后，列表接口 `/tasks`、单任务接口 `/tasks/{job_id}` 返回新标题。
- R-B.3 不回退已有 `title` 为空的行为（upload 任务 title 仍可为空，由现有 fallback 处理）。

### R-C 长视频笔记生成健壮性（最小修复）
- R-C.1 放宽 `max_tokens`（由 4096 提升至 8192），缓解正常长度视频的截断。
- R-C.2 对超长 transcript 做字符数上限保护并截断，避免超出模型上下文窗口导致 `NOTE_GENERATION_FAILED`；截断时记录 warning 日志，不中断任务。
- R-C.3 不实现分章 map-reduce（独立后续任务），本期不做。

### R-D 进度状态机约束文档化
- R-D.1 在 `db.py :: update_progress` 添加注释说明"终端态后静默丢弃更新"的语义。
- R-D.2 （可选）在 `.trellis/spec/backend/error-handling.md` 或相关 spec 补充说明，视 spec 规范而定。

## Acceptance Criteria

- [ ] AC-A.1 新增后端单测：构造多 chunk 转写场景，断言拼接后的时间戳相对于整条音频连续递增、`#t=` 秒数等于 `start 偏移 + 段相对开始`。
- [ ] AC-A.2 回归 siliconflow 分支纯文本路径不变。
- [ ] AC-B.1 新增后端单测：`update_note_content(job_id, markdown, title="新标题")` 后，`get_task` 返回的 `title` 列等于 "新标题"；`result_json.title` 也同步。
- [ ] AC-B.2 `update_note_content` 不传 title（`title=None`）时，不覆盖 DB `title` 列与现有 result_json.title。
- [ ] AC-C.1 `generate_notes` 的 `max_tokens` 提升至 8192。
- [ ] AC-D.1 `update_progress` 注释说明终端态语义。
- [ ] `uv run ruff check .` 通过。
- [ ] `uv run pytest` 通过。

## Out of Scope

- 前端编辑器/列表 UI 改造（仅后端返回正确数据即可）。
- ASR 并发分块提速（属于性能优化，非逻辑缺陷）。
- SSE 每秒轮询 DB 的优化。
- 缩略图鉴权、VTT 内联标签清理、视频时长上限等体验项。
- 取消任务后可 retry 等流程类体验改进。

## Deferred

- 分章 map-reduce 生成超长视频笔记（独立后续任务，不在本期 scope）。