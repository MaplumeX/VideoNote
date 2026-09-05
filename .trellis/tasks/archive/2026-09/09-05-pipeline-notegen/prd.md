# 子任务 C3：LLM 笔记生成重写

## Goal

重写 LLM 笔记生成阶段模块：异步 [OI] 客户端、超长转录分块 + 多块合并 + 截断续写逻辑重写，逐 chunk 可取消，错误映射到 C1 错误码体系。

## Dependencies

- 依赖 C1（09-05-pipeline-state-machine）：使用其 errors/progress 契约与 StageContext/StageResult 接口。
- 可与 C2（pipeline-transcription）并行。
- 被 C4（pipeline-orchestrator）消费。

## Scope

- `pipeline/stages/notegen.py`：
  - Async[OI] 客户端（替代同步 [OI] + to_thread）。
  - 转录分块（迁移 `_split_transcript` 60k 字符语义）、多块子笔记生成 + 合并（`_merge_notes` 语义）、`finish_reason=="length"` 续写（最多 2 次）。
  - 指数退避重试（RateLimit/超时/连接错误/5xx），迁移 `_is_retryable` 语义。
  - 双语 prompt 保留（en / zh-CN，含/无时间戳两套）。
  - 逐 chunk 之间检查取消点。
- `normalize_note_markdown`（services/markdown.py）语义保留，可迁移至新模块。
- 进度：阶段内 fraction（chunk i/n → (i+1)/n 区间映射），通过 progress 发布接口上报。

## Acceptance Criteria

- [ ] 模块签名 `async def run(ctx: StageContext) -> StageResult`，无线程、无 time.sleep（异步重试）。
- [ ] 假客户端测试覆盖：单块、多块+合并、截断续写、重试（可重试/不可重试错误）、逐 chunk 取消。
- [ ] 取消即时：await 中的 LLM 请求随 asyncio.Task.cancel() 中止，无残留调用。
- [ ] prompt/温度/max_tokens 行为与现版对齐（快照测试或参数断言）。

## Notes

- 无外部网络依赖的设计：所有测试用注入的假 Async 客户端。
