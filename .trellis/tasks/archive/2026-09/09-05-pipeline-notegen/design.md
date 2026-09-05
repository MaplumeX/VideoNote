# 技术设计：C3 LLM 笔记生成重写

> 依赖 C1 冻结契约。语义迁移自 `app/services/note_gen.py`（380 行），异步化 + 契约化重写。

## 1. 模块布局

```
backend/app/pipeline/stages/notegen.py   # NoteGenStage（phase=notegen）
```

旧 `services/note_gen.py` 不动（C4 切换后删除）。`services/markdown.py` 的 `normalize_note_markdown` 直接复用 import（它被新旧两链路共用，C4 时决定归属）。

## 2. 客户端与重试

```python
class LLMClient:
    """Async[OI] 薄封装：重试 + 续写，可注入替换（测试用 FakeLLMClient）。"""
    def __init__(self, endpoint: ProviderEndpoint): ...
    async def complete(self, messages: list[dict], *, temperature: float = 0.3,
                       max_tokens: int = 8192) -> str: ...
```

- 重试语义逐条迁移 `_llm_create_with_retry`/`_is_retryable`：最多 3 次，指数退避 2s/4s（**`asyncio.sleep` 替代 `time.sleep`**）；可重试异常 = `RateLimitError | APITimeoutError | APIConnectionError | APIStatusError(>=500)`（用 async SDK 的同名异常类型）。
- 续写语义迁移 `_call_llm`：`finish_reason == "length"` 时最多 2 次续写（messages 追加 assistant 前缀 + "Continue exactly where you left off..." user turn），仍截断则 warning。
- 重试期间收到 `asyncio.CancelledError`：立即向上抛（不被重试循环吞掉——显式 `except asyncio.CancelledError: raise` 在 except Exception 之前）。

## 3. NoteGenStage 流程

```
transcript = await ctx.artifacts.get(transcript)     # 必有（转移表保证前置）
has_timestamps = "#t=" in transcript
chunks = split_transcript(transcript, max_chars=60000)   # 迁移 _split_transcript（行边界、超长单行保序）
if len(chunks) == 1:
    notes = await client.complete([system, user])
    publish(notegen, 1.0, "Notes generated")
else:
    for i, chunk in enumerate(chunks):                   # 逐块 await，取消即时中断
        publish(notegen, (i+1)/n * 0.9, f"Generating notes {i+1}/{n}")
        sub_notes.append(await client.complete(...))
    publish(notegen, 0.9, "Merging notes...")
    merged = await client.complete(merge_messages, temperature=0.3)
    publish(notegen, 1.0, "Notes generated")
    notes = merged
return StageResult(outputs={}, extra={"notes": normalize_note_markdown(notes)})
```

- 笔记文本经 `extra` 传递（与 C2 的 audio_path 同模式；`notes` 不是 ArtifactKind——最终笔记由编排器写入 tasks.result_json，语义与旧链路一致）。若 C1 的 `notes_draft` kind 需要启用（多块中间态落库），由 C4 编排器决策，本阶段不做。
- prompt 全量迁移：`_PROMPTS_WITH/WITHOUT_TIMESTAMPS`（en/zh-CN 双语、标题上下文、转录标签）与 `_merge_notes` 的整合 prompt——**逐字符保真**，用快照测试锁定。
- resume 语义：`resume=True` 时无中间态可恢复（分块子笔记不落库），整阶段重跑——幂等且安全（LLM 调用无副作用）。

## 4. 进度映射（阶段内 fraction）

单块：0.0 → 1.0（首尾两次 publish）。多块：chunk i 完成 → `(i)/n * 0.9`；合并 → 0.9；完成 → 1.0。全程单调（PhaseProgressTracker 兜底）。

## 5. 错误处理

- LLM 异常（含重试耗尽）→ `PipelineError(NOTE_GENERATION_FAILED, detail=str(e), cause=e)`。
- transcript artifact 缺失 → `PipelineError(PROCESSING_FAILED, detail="transcript artifact missing")`（转移表破坏，理论不可达，防御性）。
- Provider 未配置完整（`ProviderEndpoint.is_complete() == False`）→ `PipelineError(PROVIDER_NOT_CONFIGURED)`（旧链路在 route 层前置校验，新链路阶段内自校验更稳）。

## 6. 测试设计（tests/pipeline/test_stage_notegen.py）

全部用注入的 `FakeLLMClient`（脚本化响应序列），零网络：
- 单块生成：prompt 断言（system/user 内容、标题上下文、无时间戳 prompt 分支）。
- 多块：split 边界（恰好 60k/超长单行）、逐块进度断言、merge prompt 断言。
- 续写：finish_reason=length 序列 → 续写消息结构断言、2 次上限后 warning。
- 重试：RateLimit→成功（断言 2 次调用 + 退避用 monkeypatch 缩短）；4xx 不重试直接抛。
- 取消：FakeClient 在 await 点抛 CancelledError → 阶段向上传播，无后续块调用（断言调用数）。
- 错误包装：PipelineError(code=NOTE_GENERATION_FAILED) 且 detail 已脱敏。
- prompt 快照：两套 prompt × 两语言逐字符断言（从旧 note_gen.py 拷贝期望值）。
