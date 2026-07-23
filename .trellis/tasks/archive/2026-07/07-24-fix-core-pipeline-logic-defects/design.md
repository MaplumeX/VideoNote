# Design — Fix core pipeline logic defects

## Architecture & Boundaries

本任务为纯后端（backend 包）逻辑缺陷修复，不涉及前端改动、不改动数据库 schema（不新增列、不新增表），不改动 API 契约（请求/响应 shape 不变）。改动集中在 `services/transcribe.py`、`services/note_gen.py`、`db.py`，外加注释/spec 说明。

## Fix A — ASR 分块时间戳偏移修正

### 现状数据流
```
_transcribe_large_file(client, audio_path, language, model, provider):
    probe 拿到 total_seconds
    chunk_duration = min(total_seconds * ratio, 600)
    for start in [0, chunk_duration, 2*chunk_duration, ...]:
        ffmpeg -ss {start} -t {chunk_duration} → chunk_path
        text = _transcribe_file(client, chunk_path, language, model, provider)
        full_transcript_parts.append(text)   # ← 未加偏移
    return "\n".join(full_transcript_parts)
```

`_transcribe_file`（OpenAI verbose_json 分支）输出形如：
```
[00:00:12](#t=12) 第一句
[00:00:45](#t=45) 第二句
```
这些时间是 Whisper 对 chunk 文件从 0 开始的相对时间。

### 修正方案
新增内部函数 `_shift_timestamps(text: str, offset_seconds: float) -> str`：
- 用正则匹配 `[HH:MM:SS](#t=SECONDS)` 中两处时间（显示时间与跳转秒数）。
- 对显示时间：解析 HH:MM:SS → 秒，加 offset，重新格式化为 `HH:MM:SS`（支持超过 60 分钟时小时位自然递增，例如 75 分钟 → 01:15:00）。
- 对跳转秒数：`int(SECONDS) + offset_seconds`（保持整数秒，与现有 `_transcribe_file` 的 `int(seg['start'])` 一致）。
- 注：`offset_seconds` 是 chunk 起始秒数（`start` 变量），非整数也不影响——显示时间用浮点加法后取整、跳转秒数取整。

只在 `_transcribe_large_file` 中对每次 `_transcribe_file` 的返回文本调用 `_shift_timestamps(text, start)` 后再 append。`_transcribe_file` 本身不变（单 chunk 独立转写场景仍正确）。

### 正则
复用 `subtitle.py` 已有时间戳格式约定。匹配模式：
```python
_TS_LINE_RE = re.compile(
    r"\[(\d{1,2}):(\d{2}):(\d{2})\]\(#t=(\d+)\)"
)
```
逐行替换，避免误伤正文里偶然出现的类似文本（LLM prompt 要求保留 `[HH:MM:SS](#t=SECONDS)` 格式，transcript 中只有 ASR 产出该格式）。

### 边界
- siliconflow 分支返回纯文本无 `#t=`，`_shift_timestamps` 找不到匹配原样返回，行为不变。
- 单 chunk（小文件）走 `_transcribe_file` 直接返回，不经过 `_shift_timestamps`，行为不变。

## Fix B — 笔记标题编辑一致性

### 现状
`db.py :: update_note_content(job_id, markdown, title)`：
- 读取 `result_json`，合并 title，写回 `result_json`。
- **不写 `tasks.title` 列**。

### 修正方案
在 `update_note_content` 的 UPDATE 语句中，把 `title` 列一起更新。SQL：
```sql
UPDATE tasks SET result_json = ?, title = ?, updated_at = ? WHERE job_id = ?
```
参数：`title` 传入时用 `title`，传入 `None` 时用 `existing_title`（保持当前 result_json 合并逻辑：`None` 不覆盖）。

具体：
- `final_title = title if title is not None else existing_title`（已有逻辑，保留）。
- UPDATE 语句把 `title` 列设为 `final_title`。

这样：
- 传新标题 → DB `title` 列与 `result_json.title` 同步更新，列表/单任务接口均返回新标题。
- 不传 title（`None`）→ `final_title = existing_title`，DB `title` 列保持原值（如果原来是视频标题则不变，如果原来是 NULL 则仍 NULL），行为与现状一致，不回退已有空值。

### 覆盖面
`update_note_content` 的调用方：`api/note_routes.py :: update_note_content_endpoint`（编辑器保存）。无其他调用方。

## Fix C — 长视频笔记生成健壮性（最小修复）

### 现状
`note_gen.py :: generate_notes`：
- `max_tokens=4096` 硬编码。
- 超长 transcript 整段塞入，无上限保护。

### 修正方案
1. `max_tokens` 由 4096 提升至 8192。
2. 在构造 user_content 前对 transcript 做字符数上限保护：
   ```python
   MAX_TRANSCRIPT_CHARS = 60000  # 约 1.5~2 小时视频的字幕量级
   if len(transcript) > MAX_TRANSCRIPT_CHARS:
       logger.warning(f"Transcript truncated: {len(transcript)} -> {MAX_TRANSCRIPT_CHARS} chars")
       transcript = transcript[:MAX_TRANSCRIPT_CHARS]
   ```
   常量定义在模块顶部。

### 边界
- 截断阈值是经验值，不做可配置（避免过度工程）。
- 截断后仍进入 LLM 生成，notes 可能不完整但不失败——优于当前的整任务失败。
- 不影响 `has_timestamps` 判定（截断不影响 `#t=` 存在性）。

## Fix D — 进度状态机约束文档化

### 现状
`db.py :: update_progress` 的 WHERE 条件 `stage NOT IN (complete, failed, cancelled)` 使终端态后的进度更新被静默丢弃。

### 修正方案
在 `update_progress` 函数 docstring 加注释说明语义：
- 终端态（complete/failed/cancelled）后，进度更新不会被写入。
- 调用方应在进入终态前完成所有进度写操作；失败后不要再写更细的错误信息（如需替换错误信息，需新提供专用接口或放开 WHERE）。

不在 `error-handling.md` 中新增条目（该 spec 描述 API 错误响应，不描述 DB 状态机内部约束），代码注释足够。

## Compatibility & Migration

- 不改 DB schema，无需迁移。
- 不改 API 契约，前端无感。
- 已有数据：B 修复后，新编辑会同步 title；历史已存在 title 与 result_json 不一致的数据无所谓（下次编辑自然对齐）。

## Trade-offs

- Fix A 用正则替换时间戳，理论上有误伤风险（transcript 正文里偶然出现 `[HH:MM:SS](#t=SECONDS)`）。但该格式是 `_transcribe_file` 机器生成的，正文不会出现，风险可忽略。
- Fix C 截断阈值 60000 是经验值，不覆盖所有模型上下文窗口差异；但作为最小修复，比当前的"失败"或"截断 4096"显著改善。