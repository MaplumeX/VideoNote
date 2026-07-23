# Implement — Fix core pipeline logic defects

## Ordered Checklist

### A. ASR 分块时间戳偏移修正
- [ ] A.1 在 `backend/app/services/transcribe.py` 顶部 `import re`（若缺失）并定义模块级 `_TS_LINE_RE`，匹配 `[HH:MM:SS](#t=SECONDS)`。
- [ ] A.2 新增 `_shift_timestamps(text: str, offset_seconds: float) -> str`：逐行用 `_TS_LINE_RE` 查找，把显示时间 HH:MM:SS 解析为秒并加偏移重新格式化、把 `#t=SECONDS` 加偏移取整。
- [ ] A.3 在 `_transcribe_large_file` 的 `full_transcript_parts.append(text)` 处改为 `append(_shift_timestamps(text, start))`。
- [ ] A.4 新增单测到 `backend/tests/test_pipeline_bugs.py`：
  - `test_shift_timestamps_adds_chunk_offset`：构造 chunk 输出（含两行 `#t=`），偏移 600.0，断言显示时间与跳转秒数都 +600。
  - `test_shift_timestamps_passthrough_no_timestamps`：纯文本无 `#t=` 原样返回（覆盖 siliconflow 路径）。
  - `test_transcribe_large_file_offsets_chunk_timestamps`：mock `_transcribe_file` 返回固定带时间戳文本、mock probe duration/ffmpeg split，断言拼接结果中第二块时间戳带 `chunk_duration` 偏移。

### B. 笔记标题编辑一致性
- [ ] B.1 修改 `backend/app/db.py :: update_note_content` 的 UPDATE 语句：增加 `title = ?` 列，绑定 `final_title`。
- [ ] B.2 新增单测到 `backend/tests/test_core_reliability.py`：
  - `test_update_note_content_syncs_title_column`：用 `isolated_db` fixture，create_task 后 `update_note_content(job_id, "...", title="新标题")`，`get_task` 返回 `title == "新标题"`，`result_json.title == "新标题"`。
  - `test_update_note_content_preserves_title_when_none`：`update_note_content(job_id, "...", title=None)`，断言不覆盖原 title。

### C. 长视频笔记生成健壮性（最小修复）
- [ ] C.1 修改 `backend/app/services/note_gen.py`：`max_tokens=4096` → `max_tokens=8192`。
- [ ] C.2 在模块顶部定义 `MAX_TRANSCRIPT_CHARS = 60000`，在构造 `user_content` 前对 `transcript` 做长度检查并截断 + warning 日志。
- [ ] C.3 新增单测到 `backend/tests/test_pipeline_bugs.py`：
  - `test_generate_notes_truncates_long_transcript`：mock OpenAI client，传入超长 transcript（>60000 字符），断言传给 client 的 messages 内容被截断（长度 <= 60000 + prompt 固定部分）。
  - `test_generate_notes_max_tokens_is_8192`：mock client，断言 `create()` 调用 kwargs `max_tokens == 8192`。

### D. 进度状态机约束文档化
- [ ] D.1 在 `backend/app/db.py :: update_progress` 的 docstring 补充说明：终端态（complete/failed/cancelled）后进度更新被静默丢弃；调用方应在进入终态前完成所有进度写。

### 验证
- [ ] V.1 `cd backend && uv run ruff check .`
- [ ] V.2 `cd backend && uv run pytest`
- [ ] V.3 通读 diff 确认无无关改动。

## Validation Commands

```bash
cd backend
uv run ruff check .
uv run pytest -q
```

## Risky Files / Rollback Points

- `backend/app/services/transcribe.py`：Fix A 核心改动。回滚点 = 还原 `_shift_timestamps` 调用为直接 append。
- `backend/app/db.py`：Fix B + Fix D。回滚点 = UPDATE 语句去掉 `title` 列。
- `backend/app/services/note_gen.py`：Fix C。回滚点 = `max_tokens` 改回 4096 + 去掉截断。

## Sub-agent Dispatch Notes

- sub-agent dispatchers（trellis-implement / trellis-check）的 prompt 必须以 `Active task: .trellis/tasks/07-24-fix-core-pipeline-logic-defects` 开头。
- `implement.jsonl` / `check.jsonl` 需各含至少一条真实 spec 条目（见下）。