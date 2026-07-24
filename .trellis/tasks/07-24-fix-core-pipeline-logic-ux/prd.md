# Fix core pipeline logic bugs and UX issues

## Goal

修复 VideoNote 核心链路(提交 → 字幕/ASR → LLM 笔记 → 前端进度展示)中已发现的逻辑 bug 与体验问题,覆盖前后端 13 项,使长视频任务稳定可见、错误信息可自助排查、取消/重试行为正确。

## Background

代码审查发现核心链路存在以下问题,影响可靠性、可观测性与可维护性:

### 一、逻辑 bug(P0/P1)

1. **SSE 重连配额被正常关闭耗尽 → 长视频任务断连**
   - `frontend/src/hooks/useSSE.ts` 中 `reconnectAttempt` 从不在成功建连后重置。
   - 后端 SSE 端点 `MAX_DURATION = 30 * 60` 主动关闭连接(frontend reconnects automatically),每次正常关闭都消耗一次重连配额,达到 `MAX_RECONNECT_ATTEMPTS = 3` 后展示"连接丢失"。
   - 长视频(ASR + 多 chunk LLM 合并)实际处理时长超过 ~90 min 即丢失进度展示。

2. **retry 上传文件任务时前端把 `source_type` 硬编码为 `"url"`**
   - `frontend/src/pages/NewNotePage.tsx` 的 `handleRetry` 固定写入 `source_type: "url"`,但后端 `retry_task` 的 upload 分支返回 `platform="upload"`。
   - `StepIndicator` 按错误的 URL 流程渲染步骤,且 `VideoInfoCard` 无 title/thumbnail。

3. **提交 URL 时 NewNotePage 信息卡空**
   - `process_video` 路由正常与 dedup 分支都返回 `title="", thumbnail_url=""`。
   - SSE `progress` 事件只携带 `stage/progress/message`,不带 title/thumbnail。
   - dedup 分支即使 DB 里已有活动任务的 title/thumbnail 也直接丢弃。

4. **ASR 语言映射不覆盖日语等**
   - `routes.py` 的 `_asr_language` 仅映射 zh/en,但 `_subtitle_languages` 含 `ja`。
   - 走 ASR 的日文视频被传 `language="en"`,转录质量差。

### 二、体验问题(P1/P2/P3)

5. **错误信息不透传,用户只看到固定 code**
   - `_process_video_url` / `_process_video_file` 的 except 分支把错误码写成固定字符串,原始异常消息只进日志不进 `message` 字段。
   - 鉴权失败、欠费、模型不存在、网络超时等 UI 侧无法区分。

6. **上传过程中 token 过期,即使 refresh 成功也失败**
   - `useVideoUpload.ts` 的 401 分支 `silentRefresh()` 成功后仍 `resolve("")`,要求用户重新选文件。

7. **Provider 未配置时缺少前置校验**
   - `_get_user_provider` 返回 None 时空 `api_key` 最终在 OpenAI/Whisper 调用处抛鉴权错,再被固定码吞掉。
   - 应在 `/process` / `/upload` 入口给出明确的 `PROVIDER_NOT_CONFIGURED`。

8. **NoteDetailPage retry 后旧记录与新记录并存**
   - `retry_task` 创建新 job_id 不删旧 failed 任务,出现"一条 failed + 一条 complete"。至少需 UI 提示。

9. **`extract_subtitles` 重复跑 yt-dlp extract_info**
   - 先 `extract_info(download=False)` 探测存在性,再 `_download_and_read_subtitle` 重新 `download([url])`(内部又 extract_info),元数据接口跑两遍,徒增首帧延迟。

10. **取消在 extract_info(download=False) 阶段不响应**
    - `_cancel_hook` 是 `progress_hooks`,`extract_info(url, download=False)` 不产生下载进度,hook 不触发。
    - 取消请求在该阶段不生效,要等到进入下载/ASR。

### 三、代码异味(P3,顺手清理)

11. **`_process_video_url` 与 `_process_video_file` 大段重复**
    - provider 解析 + ASR 调用 + note generation 调用 + 异常处理在两函数中几乎逐字重复,任何一处修复都要改两遍。

12. **`upload_video` 的 `safe_name` 处理偏弱**
    - 单次 `replace("..", "")` 对 `....//` 之类不能完全防御;建议末段名 + 白名单字符替换。

13. **retry upload 复用旧 `input_file_path` 不拷贝**
    - 新任务完成后 `_process_video_file` 的 finally 会 `unlink` 旧文件,原 failed 任务的 `input_file_path` 指向已删文件,再次 retry 原 failed 任务会 `UPLOAD_FILE_MISSING`。

## Requirements

### R1 SSE 重连与长任务可见性
- R1.1 在成功建立 SSE 连接并收到首个事件后,`reconnectAttempt` 必须重置为 0。
- R1.2 `fetchTaskById` 恢复后若任务仍在 processing,视为正常重连而非失败,不消耗重连配额。
- R1.3 网络抖动导致的 "建连即断" 仍按指数退避重试,最多 3 次。

### R2 Retry 行为正确
- R2.1 `retry_task` 的 upload 分支返回结果,前端必须按 `platform === "upload"` 决定 `source_type`,不再硬编码 `"url"`。
- R2.2 后端 `ProcessResponse` 增加 `source_type` 字段,前端直接使用,避免推断错误。

### R3 提交 URL 视频信息可见
- R3.1 SSE `progress` 事件附带 `title` 与 `thumbnail_url`(后端 `update_task_meta` 后下一次 SSE 轮询携带)。
- R3.2 前端收到带 title/thumbnail 的 progress 事件后更新 `taskMeta`,`VideoInfoCard` 立即显示。
- R3.3 dedup 分支返回 DB 中已有的 title/thumbnail。

### R4 ASR 语言映射对齐
- R4.1 `_asr_language` 至少覆盖 en / zh / ja,与 `_subtitle_languages` 保持一致。
- R4.2 其他未覆盖语言回退到不传 language(让 Whisper 自动探测),不强制 `en`。

### R5 错误信息透传
- R5.1 每个失败分支在写入错误码的同时,把可展示的异常摘要(去敏感:API key、完整 URL)写入 `message` 字段,格式 `<CODE>: <摘要>` 或保留前端的 code 翻译逻辑同时携带 detail。
- R5.2 前端 `translateTaskMessage` 能识别带 detail 的 message 并友好展示。

### R6 上传 token 过期自动重发
- R6.1 `useVideoUpload` 在 401 且 `silentRefresh()` 成功时,使用新 token 自动重发同一上传请求,不要求用户重新选文件。
- R6.2 refresh 失败仍按原行为提示会话过期。

### R7 Provider 前置校验
- R7.1 `/process` 在调度前检查 ASR 与 LLM provider 是否齐备(api_key 非空),缺失返回 `PROVIDER_NOT_CONFIGURED`。
- R7.2 `/upload` 同样校验。
- R7.3 未配置时前端引导用户去设置页(在错误处理中匹配该 code)。

### R8 取消响应性
- R8.1 在 `get_video_info_strict` 与 `extract_subtitles` 首次 `extract_info(download=False)` 调用前后增加 `cancel_event.is_set()` 检查,使取消在 extract_info 完成后立即生效。
- R8.2 不得引入阻塞主事件循环的轮询。

### R9 字幕提取去重
- R9.1 `extract_subtitles` 单次 `download` 调用内拿到字幕内容,不再重复 `extract_info(download=False)` 探测。
- R9.2 行为对调用方保持等价:无字幕仍返回 None 触发 ASR 回退。

### R10 retry upload 文件所有权
- R10.1 `retry_task` 的 upload 分支在复用旧 `input_file_path` 时,拷贝一份给新任务,或显式标记"原 failed 任务不可再次 retry"。
- R10.2 不破坏现有 `cleanup_failed_task_files` 的路径安全约束。

### R11 主流程去重(代码异味)
- R11.1 抽出 `resolve_providers(user_id)` / `run_asr(...)` / `run_note_gen(...)` 三个 helper,`_process_video_url` 与 `_process_video_file` 只保留各自获取 transcript 的差异部分。
- R11.2 行为对调用方等价;现有测试不回归。

### R12 upload safe_name 加固
- R12.1 `safe_name` 取 `Path(filename).name` 后做白名单字符替换,禁止 `..` 之外的其他路径分隔符。
- R12.2 验证最终路径仍位于 `UPLOAD_DIR` 之下。

## Acceptance Criteria

- [ ] AC1 长视频任务 SSE 不再因正常关闭断连:`reconnectAttempt` 在成功建连并收到首个事件后归零;模拟"30 min 超时关闭"后仍能继续恢复进度(单测覆盖)。
- [ ] AC2 retry upload 任务时 `StepIndicator` 按 upload 流程渲染;`VideoInfoCard` 不再靠空字段渲染。
- [ ] AC3 提交 URL 后,当后端 `update_task_meta` 完成时,SSE progress 事件携带 title/thumbnail,前端 `VideoInfoCard` 立即更新。
- [ ] AC4 日文视频走 ASR 时 `language` 传 `ja`;其他未映射语言回退为自动探测而非 `en`。
- [ ] AC5 鉴权失败 / 欠费 / 模型不存在 / 网络超时四种情况,前端能看到可区分的错误信息(单测覆盖 message 透传)。
- [ ] AC6 上传过程中 access token 过期且 refresh 成功时,上传自动重发并继续。
- [ ] AC7 未配置 provider 提交 URL/上传,前端显示明确错误并引导去设置页。
- [ ] AC8 在 `extract_info(download=False)` 完成后取消能立即响应(单测或集成验证)。
- [ ] AC9 `extract_subtitles` 仅调用一次 yt-dlp `download`/`extract_info` 即返回内容或 None。
- [ ] AC10 retry upload 不破坏原 failed 任务的 `input_file_path` 语义;或显式拷贝使两次 retry 都可成功。
- [ ] AC11 `_process_video_url` / `_process_video_file` 重复段抽为 helper,现有 `test_core_reliability` / `test_pipeline_bugs` 全部通过。
- [ ] AC12 `safe_name` 加固后路径越界测试通过。

## Out of Scope

- 跨进程任务编排 / 外部任务队列(当前单进程 TaskRunner 已足够)。
- 日文之外的其他语种 ASR 精细映射(本期仅 en/zh/ja + 自动探测)。
- 历史"一条 failed + 一条 complete"两条记录的批量去重 UI(本期只在 retry 交互上做最小提示,不做自动合并)。

## Notes

- 遵循 `.trellis/spec/backend/` 与 `.trellis/spec/frontend/` 规范。
- 错误处理参考 `.trellis/spec/backend/error-handling.md`。
- Hook 改动参考 `.trellis/spec/frontend/hook-guidelines.md`。
- 所有修改须保持现有测试通过,并按需要新增覆盖。