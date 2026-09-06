"""Tests for the notegen stage (C3): fake LLM clients, zero network.

Retry/continuation tests stub the innermost ``chat.completions.create``
call on a real ``LLMClient`` instance so the actual retry loop and
continuation logic are exercised.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    BadRequestError,
    RateLimitError,
)

from app.pipeline.errors import ErrorCode, PipelineError
from app.pipeline.stages.base import (
    ArtifactStore,
    ProviderConfig,
    ProviderEndpoint,
    StageContext,
)
from app.pipeline.stages.notegen import (
    MAX_TRANSCRIPT_CHARS,
    LLMClient,
    NoteGenStage,
    _build_generation_messages,
    _build_merge_messages,
    split_transcript,
)
from app.pipeline.state import ArtifactKind, PipelinePhase

# --- Test doubles -----------------------------------------------------------


def _httpx_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("POST", "http://test"))


def rate_limit_error() -> RateLimitError:
    return RateLimitError("rate limited", response=_httpx_response(429), body=None)


def bad_request_error() -> BadRequestError:
    return BadRequestError("bad request", response=_httpx_response(400), body=None)


def server_error() -> APIStatusError:
    return APIStatusError("server error", response=_httpx_response(500), body=None)


def timeout_error() -> APITimeoutError:
    return APITimeoutError(request=httpx.Request("POST", "http://test"))


def connection_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("POST", "http://test"))


class FakeResponseObj:
    """Mimics the SDK response shape (choices[0].message.content / finish_reason)."""

    def __init__(self, content: str, finish_reason: str) -> None:
        msg = type("Msg", (), {"content": content})()
        self.choices = [type("Choice", (), {"message": msg, "finish_reason": finish_reason})()]


class FakeCompletions:
    """Scripted chat.completions.create: pops outcomes, records kwargs."""

    def __init__(self, outcomes: list) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    async def create(self, **kwargs) -> object:
        self.calls.append(kwargs)
        item = self.outcomes.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeAsyncOpenAI:
    def __init__(self, outcomes: list) -> None:
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(outcomes)


def make_llm_client(outcomes: list) -> tuple[LLMClient, FakeCompletions]:
    """Build a real LLMClient with the innermost SDK client stubbed out."""
    client = LLMClient.__new__(LLMClient)  # skip __init__ (no real OpenAI client)
    client._endpoint = ProviderEndpoint(api_key="k", api_base="b", model="gpt-test")
    fake = FakeAsyncOpenAI(outcomes)
    client._client = fake  # type: ignore[assignment]
    return client, fake.chat.completions


class FakeLLMClient:
    """LLMClient-protocol fake for NoteGenStage tests: pops scripted strings."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def complete(
        self, messages: list[dict], *, temperature: float = 0.3, max_tokens: int = 8192
    ) -> str:
        self.calls.append(
            {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        )
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class CancellingClient:
    """Raises CancelledError at the Nth complete() call (await-point cancel)."""

    def __init__(self, fail_on_call: int) -> None:
        self.fail_on_call = fail_on_call
        self.calls = 0

    async def complete(
        self, messages: list[dict], *, temperature: float = 0.3, max_tokens: int = 8192
    ) -> str:
        self.calls += 1
        if self.calls >= self.fail_on_call:
            raise asyncio.CancelledError()
        return "sub"


class MemoryArtifacts(ArtifactStore):
    def __init__(self, store: dict | None = None) -> None:
        self.store = store or {}

    async def get(self, kind) -> object | None:
        return self.store.get(kind)

    async def put(self, kind, content) -> None:
        self.store[kind] = content


class ProgressRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[PipelinePhase, float, str]] = []

    async def publish(self, phase: PipelinePhase, fraction: float, message: str) -> None:
        self.events.append((phase, fraction, message))


def make_ctx(
    transcript: str,
    *,
    language: str = "en",
    meta: dict | None = None,
) -> tuple[StageContext, ProgressRecorder]:
    store: dict = {ArtifactKind.transcript: transcript}
    if meta is not None:
        store[ArtifactKind.video_meta] = meta
    recorder = ProgressRecorder()
    ctx = StageContext(
        job_id="job-1",
        language=language,
        provider=ProviderConfig(
            llm=ProviderEndpoint(api_key="sk-testkey", api_base="http://llm", model="gpt-test")
        ),
        artifacts=MemoryArtifacts(store),
        progress=recorder,
        register_cancel=lambda handle: None,
    )
    return ctx, recorder


TIMESTAMPED = "hello [00:00:01](#t=1)\nworld [00:00:02](#t=2)"


def multi_chunk_transcript(lines: int = 601) -> str:
    # 601 lines of 100 chars -> >60000 chars -> multiple chunks at line boundaries.
    return ("a" * 99 + "\n") * lines


@pytest.fixture()
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record asyncio.sleep durations instead of actually waiting."""
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return recorded


# --- split_transcript -------------------------------------------------------


def test_split_short_transcript_single_chunk() -> None:
    assert split_transcript("a\nb\nc") == ["a\nb\nc"]


def test_split_exactly_at_limit_single_chunk() -> None:
    transcript = "x" * MAX_TRANSCRIPT_CHARS
    assert split_transcript(transcript) == [transcript]


def test_split_at_line_boundaries() -> None:
    lines = ["x" * 10, "y" * 10]
    chunks = split_transcript("\n".join(lines), max_chars=11)
    assert chunks == ["x" * 10, "y" * 10]


def test_split_oversize_single_line_kept_as_is() -> None:
    transcript = "x" * (MAX_TRANSCRIPT_CHARS + 5)
    chunks = split_transcript(transcript, max_chars=10)
    assert chunks == [transcript]


# --- Single chunk -----------------------------------------------------------


async def test_single_chunk_generation_prompt_and_progress() -> None:
    client = FakeLLMClient(["# Notes\n\n- point"])
    ctx, recorder = make_ctx(TIMESTAMPED)
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    result = await stage.run(ctx, resume=False)

    assert len(client.calls) == 1
    call = client.calls[0]
    messages = call["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    # Has timestamps -> WITH_TIMESTAMPS prompt
    assert "with timestamps" in messages[0]["content"]
    assert "#t=SECONDS" in messages[0]["content"]
    # User content embeds the transcript
    assert TIMESTAMPED in messages[1]["content"]
    assert call["temperature"] == 0.3
    assert call["max_tokens"] == 8192
    # Result: normalized notes via extra, no artifacts written
    assert result.outputs == {}
    assert result.extra["notes"] == "# Notes\n\n- point"
    # Progress: start + done
    assert recorder.events == [
        (PipelinePhase.notegen, 0.0, "Generating notes..."),
        (PipelinePhase.notegen, 1.0, "Notes generated"),
    ]


async def test_single_chunk_without_timestamps_uses_no_timestamp_prompt() -> None:
    client = FakeLLMClient(["notes"])
    ctx, _ = make_ctx("plain transcript, no timestamps")
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    await stage.run(ctx, resume=False)

    system = client.calls[0]["messages"][0]["content"]
    assert "does not contain timestamps" in system
    assert "#t=SECONDS" not in system


async def test_video_title_context_from_meta() -> None:
    client = FakeLLMClient(["notes"])
    ctx, _ = make_ctx(TIMESTAMPED, meta={"title": "My Video"})
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    await stage.run(ctx, resume=False)

    user = client.calls[0]["messages"][1]["content"]
    assert "\n\nVideo title: My Video\n\n" in user

    # Chinese variant
    client_zh = FakeLLMClient(["notes"])
    ctx_zh, _ = make_ctx(TIMESTAMPED, language="zh-CN", meta={"title": "我的视频"})
    stage_zh = NoteGenStage(client=client_zh)  # type: ignore[arg-type]
    await stage_zh.run(ctx_zh, resume=False)
    user_zh = client_zh.calls[0]["messages"][1]["content"]
    assert "\n\n视频标题：我的视频\n\n" in user_zh


async def test_notes_normalized_via_extra() -> None:
    fenced = "```markdown\n# Title\n\nbody\n```"
    client = FakeLLMClient([fenced])
    ctx, _ = make_ctx(TIMESTAMPED)
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    result = await stage.run(ctx, resume=False)
    assert result.extra["notes"] == "# Title\n\nbody"


# --- Multi chunk ------------------------------------------------------------


async def test_multi_chunk_generate_and_merge() -> None:
    transcript = multi_chunk_transcript()
    n_chunks = len(split_transcript(transcript))
    assert n_chunks >= 2
    client = FakeLLMClient([*[f"sub{i}" for i in range(n_chunks)], "merged notes"])
    ctx, recorder = make_ctx(transcript)
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    result = await stage.run(ctx, resume=False)

    # n generation calls + 1 merge call
    assert len(client.calls) == n_chunks + 1
    # Merge call prompt (en)
    merge_messages = client.calls[-1]["messages"]
    assert "note integration assistant" in merge_messages[0]["content"]
    combined = "\n\n---\n\n".join(f"sub{i}" for i in range(n_chunks))
    assert merge_messages[1]["content"] == (
        f"Please integrate the following note drafts:\n\n{combined}"
    )
    assert result.extra["notes"] == "merged notes"
    # Progress sequence: per-chunk, merge, done. The last chunk publishes
    # n/n * 0.9 == 0.9 (same value as the merge publish — monotonic-safe).
    assert recorder.events[-3] == (
        PipelinePhase.notegen,
        0.9,
        f"Generating notes {n_chunks}/{n_chunks}",
    )
    assert recorder.events[-2] == (PipelinePhase.notegen, 0.9, "Merging notes...")
    assert recorder.events[-1] == (PipelinePhase.notegen, 1.0, "Notes generated")


async def test_multi_chunk_progress_monotonic() -> None:
    transcript = multi_chunk_transcript()
    n_chunks = len(split_transcript(transcript))
    client = FakeLLMClient([*[f"sub{i}" for i in range(n_chunks)], "merged"])
    ctx, recorder = make_ctx(transcript)
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    await stage.run(ctx, resume=False)
    fractions = [f for _, f, _ in recorder.events]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0
    assert len(fractions) == n_chunks + 2  # n chunk publishes + merge + done


async def test_multi_chunk_merge_prompt_zh() -> None:
    transcript = multi_chunk_transcript()
    n_chunks = len(split_transcript(transcript))
    client = FakeLLMClient([*[f"子{i}" for i in range(n_chunks)], "合并"])
    ctx, _ = make_ctx(transcript, language="zh-CN")
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    await stage.run(ctx, resume=False)
    merge_messages = client.calls[-1]["messages"]
    assert "笔记整合助手" in merge_messages[0]["content"]
    assert "请整合以下多段笔记草稿：" in merge_messages[1]["content"]
    assert "\n\n---\n\n" in merge_messages[1]["content"]


# --- Continuation (finish_reason == "length") -------------------------------


async def test_continuation_up_to_two_times() -> None:
    client, completions = make_llm_client(
        [
            FakeResponseObj("part1", "length"),
            FakeResponseObj("part2", "length"),
            FakeResponseObj("part3", "stop"),
        ]
    )
    result = await client.complete(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    )
    assert result == "part1part2part3"
    assert len(completions.calls) == 3
    # Continuation message structure
    cont_messages = completions.calls[1]["messages"]
    assert cont_messages[0] == {"role": "system", "content": "s"}
    assert cont_messages[1] == {"role": "user", "content": "u"}
    assert cont_messages[2] == {"role": "assistant", "content": "part1"}
    assert cont_messages[3]["role"] == "user"
    assert cont_messages[3]["content"] == (
        "Continue exactly where you left off. "
        "Do not repeat, do not wrap in a code block."
    )
    second_cont = completions.calls[2]["messages"]
    assert second_cont[2] == {"role": "assistant", "content": "part1part2"}


async def test_continuation_still_truncated_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, completions = make_llm_client(
        [
            FakeResponseObj("part1", "length"),
            FakeResponseObj("part2", "length"),
            FakeResponseObj("part3", "length"),
        ]
    )
    with caplog.at_level("WARNING", logger="app.pipeline.stages.notegen"):
        result = await client.complete([{"role": "user", "content": "u"}])
    assert result == "part1part2part3"
    assert len(completions.calls) == 3  # capped at 2 continuations
    assert any(
        "still truncated after 2 continuations" in r.message for r in caplog.records
    )


async def test_completion_params_passed_to_sdk() -> None:
    client, completions = make_llm_client([FakeResponseObj("ok", "stop")])
    await client.complete(
        [{"role": "user", "content": "u"}], temperature=0.7, max_tokens=1024
    )
    assert completions.calls == [
        {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "u"}],
            "temperature": 0.7,
            "max_tokens": 1024,
        }
    ]


# --- Retry ------------------------------------------------------------------


async def test_retry_rate_limit_then_success(sleeps: list[float]) -> None:
    client, completions = make_llm_client(
        [rate_limit_error(), FakeResponseObj("ok", "stop")]
    )
    result = await client.complete([{"role": "user", "content": "u"}])
    assert result == "ok"
    assert len(completions.calls) == 2
    assert sleeps == [2.0]


async def test_retry_all_transient_errors_retryable(sleeps: list[float]) -> None:
    # Budget is 3 attempts: rate-limit + timeout then success.
    client, completions = make_llm_client(
        [rate_limit_error(), timeout_error(), FakeResponseObj("ok", "stop")]
    )
    result = await client.complete([{"role": "user", "content": "u"}])
    assert result == "ok"
    assert len(completions.calls) == 3
    assert sleeps == [2.0, 4.0]


async def test_retry_connection_and_5xx_status_retryable(sleeps: list[float]) -> None:
    client, completions = make_llm_client(
        [connection_error(), server_error(), FakeResponseObj("ok", "stop")]
    )
    result = await client.complete([{"role": "user", "content": "u"}])
    assert result == "ok"
    assert len(completions.calls) == 3


async def test_retry_budget_exhausted_raises(sleeps: list[float]) -> None:
    client, completions = make_llm_client(
        [rate_limit_error(), rate_limit_error(), rate_limit_error()]
    )
    with pytest.raises(RateLimitError):
        await client.complete([{"role": "user", "content": "u"}])
    assert len(completions.calls) == 3
    assert sleeps == [2.0, 4.0]


async def test_non_retryable_error_raises_immediately(sleeps: list[float]) -> None:
    client, completions = make_llm_client([bad_request_error()])
    with pytest.raises(BadRequestError):
        await client.complete([{"role": "user", "content": "u"}])
    assert len(completions.calls) == 1
    assert sleeps == []


async def test_cancelled_error_not_swallowed_by_retry_loop(
    sleeps: list[float],
) -> None:
    # The scripted outcome raises CancelledError on attempt 1: it must
    # propagate immediately (not retried, not treated as a response).
    client, completions = make_llm_client([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await client.complete([{"role": "user", "content": "u"}])
    assert len(completions.calls) == 1
    assert sleeps == []


# --- Cancellation at stage level --------------------------------------------


async def test_cancellation_propagates_and_stops_further_chunks() -> None:
    transcript = multi_chunk_transcript(lines=1201)  # -> 3 chunks
    n_chunks = len(split_transcript(transcript))
    assert n_chunks >= 3
    client = CancellingClient(fail_on_call=2)
    ctx, _ = make_ctx(transcript)
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    with pytest.raises(asyncio.CancelledError):
        await stage.run(ctx, resume=False)
    # Cancelled during chunk 2: chunk 3 never starts, no merge call.
    assert client.calls == 2
    assert client.calls < n_chunks + 1


# --- Error wrapping ---------------------------------------------------------


async def test_llm_error_wrapped_as_note_generation_failed() -> None:
    client = FakeLLMClient([bad_request_error()])
    ctx, _ = make_ctx(TIMESTAMPED)
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    with pytest.raises(PipelineError) as exc_info:
        await stage.run(ctx, resume=False)
    assert exc_info.value.code == ErrorCode.NOTE_GENERATION_FAILED
    assert exc_info.value.detail  # sanitized detail present
    assert exc_info.value.__cause__ is not None


async def test_llm_error_detail_sanitized() -> None:
    leak = RuntimeError("boom with sk-abcdefghijklmnop1234 and Bearer abc.def.ghi")
    client = FakeLLMClient([leak])
    ctx, _ = make_ctx(TIMESTAMPED)
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    with pytest.raises(PipelineError) as exc_info:
        await stage.run(ctx, resume=False)
    assert "sk-abcdefghijklmnop1234" not in exc_info.value.detail
    assert "[REDACTED]" in exc_info.value.detail


async def test_missing_transcript_artifact_is_processing_failed() -> None:
    client = FakeLLMClient(["notes"])
    recorder = ProgressRecorder()
    ctx = StageContext(
        job_id="job-1",
        language="en",
        provider=ProviderConfig(
            llm=ProviderEndpoint(api_key="k", api_base="b", model="m")
        ),
        artifacts=MemoryArtifacts({}),
        progress=recorder,
        register_cancel=lambda handle: None,
    )
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    with pytest.raises(PipelineError) as exc_info:
        await stage.run(ctx, resume=False)
    assert exc_info.value.code == ErrorCode.PROCESSING_FAILED
    assert exc_info.value.detail == "transcript artifact missing"
    assert client.calls == []


async def test_incomplete_provider_config_rejected() -> None:
    client = FakeLLMClient(["notes"])
    recorder = ProgressRecorder()
    ctx = StageContext(
        job_id="job-1",
        language="en",
        provider=ProviderConfig(
            llm=ProviderEndpoint(api_key="", api_base="b", model="m")
        ),
        artifacts=MemoryArtifacts({ArtifactKind.transcript: "text"}),
        progress=recorder,
        register_cancel=lambda handle: None,
    )
    stage = NoteGenStage(client=client)  # type: ignore[arg-type]
    with pytest.raises(PipelineError) as exc_info:
        await stage.run(ctx, resume=False)
    assert exc_info.value.code == ErrorCode.PROVIDER_NOT_CONFIGURED
    assert client.calls == []


# --- Prompt snapshots (character-for-character, from legacy note_gen.py) -----


def test_prompt_snapshot_en_with_timestamps() -> None:
    messages = _build_generation_messages("TR", "Title", "en", True)
    assert messages[0]["content"] == (
        "You are a professional note-taking assistant. "
        "Given a video transcript with timestamps, "
        "generate well-structured Markdown notes.\n\n"
        "Rules:\n"
        "1. Use proper heading hierarchy (##, ###) to organize topics\n"
        "2. Include bullet points for key information\n"
        "3. Preserve timestamps from the transcript as clickable links "
        "in the format [HH:MM:SS](#t=SECONDS)\n"
        "4. Summarize the main points concisely - "
        "don't just repeat the transcript\n"
        "5. If the transcript has clear sections, "
        "create a summary for each section\n"
        "6. Add a brief overall summary at the top\n"
        "7. Write notes in the same language as the transcript "
        "(Chinese for Chinese, English for English)\n"
        "8. Return only the Markdown document. Do not wrap it in a code block.\n"
    )
    assert messages[1]["content"] == (
        "Please generate structured Markdown notes from the following video transcript."
        "\n\nVideo title: Title\n\nTranscript:\nTR"
    )


def test_prompt_snapshot_en_without_timestamps_no_title() -> None:
    messages = _build_generation_messages("TR", None, "en", False)
    assert messages[0]["content"] == (
        "You are a professional note-taking assistant. "
        "Given a video transcript, "
        "generate well-structured Markdown notes.\n\n"
        "Rules:\n"
        "1. Use proper heading hierarchy (##, ###) to organize topics\n"
        "2. Include bullet points for key information\n"
        "3. The transcript does not contain timestamps, "
        "so do not add any timestamps\n"
        "4. Summarize the main points concisely - "
        "don't just repeat the transcript\n"
        "5. If the transcript has clear sections, "
        "create a summary for each section\n"
        "6. Add a brief overall summary at the top\n"
        "7. Write notes in the same language as the transcript "
        "(Chinese for Chinese, English for English)\n"
        "8. Return only the Markdown document. Do not wrap it in a code block.\n"
    )
    assert messages[1]["content"] == (
        "Please generate structured Markdown notes from the following video transcript."
        "\n\nTranscript:\nTR"
    )


def test_prompt_snapshot_zh_with_timestamps() -> None:
    messages = _build_generation_messages("TR", "标题", "zh-CN", True)
    assert messages[0]["content"] == (
        "你是一位专业的笔记助手。"
        "给定带有时间戳的视频转录文本，"
        "生成结构化的 Markdown 笔记。\n\n"
        "规则：\n"
        "1. 使用合适的标题层级（##、###）组织主题\n"
        "2. 用要点列出关键信息\n"
        "3. 保留转录文本中的时间戳，"
        "以可点击链接格式 [HH:MM:SS](#t=SECONDS) 呈现\n"
        "4. 简明扼要地总结要点 - 不要照搬转录文本\n"
        "5. 如果转录文本有明显段落，为每段生成摘要\n"
        "6. 在顶部添加简要总览\n"
        "7. 用中文撰写笔记\n"
        "8. 只返回 Markdown 文档本身，不要包裹在代码块中。\n"
    )
    assert messages[1]["content"] == (
        "请根据以下视频转录文本生成结构化的 Markdown 笔记。"
        "\n\n视频标题：标题\n\n转录文本:\nTR"
    )


def test_prompt_snapshot_zh_without_timestamps() -> None:
    messages = _build_generation_messages("TR", None, "zh-CN", False)
    assert messages[0]["content"] == (
        "你是一位专业的笔记助手。"
        "给定视频转录文本，"
        "生成结构化的 Markdown 笔记。\n\n"
        "规则：\n"
        "1. 使用合适的标题层级（##、###）组织主题\n"
        "2. 用要点列出关键信息\n"
        "3. 转录文本不包含时间戳，因此不要添加任何时间戳\n"
        "4. 简明扼要地总结要点 - 不要照搬转录文本\n"
        "5. 如果转录文本有明显段落，为每段生成摘要\n"
        "6. 在顶部添加简要总览\n"
        "7. 用中文撰写笔记\n"
        "8. 只返回 Markdown 文档本身，不要包裹在代码块中。\n"
    )
    assert messages[1]["content"] == (
        "请根据以下视频转录文本生成结构化的 Markdown 笔记。"
        "\n\n转录文本:\nTR"
    )


def test_prompt_snapshot_unknown_lang_falls_back_to_en() -> None:
    messages = _build_generation_messages("TR", None, "fr", False)
    assert "does not contain timestamps" in messages[0]["content"]
    assert messages[1]["content"] == (
        "Please generate structured Markdown notes from the following video transcript."
        "\n\nTranscript:\nTR"
    )


def test_merge_prompt_snapshot_en() -> None:
    messages = _build_merge_messages(["A", "B"], "T", "en")
    assert messages[0]["content"] == (
        "You are a note integration assistant. Below are multiple note drafts "
        "from the same video, concatenated in order. "
        "Merge them into a single coherent Markdown note:\n"
        "1. Unify heading hierarchy (## for major topics, ### for subtopics)\n"
        "2. Remove duplicates\n"
        "3. Add a brief overview at the top\n"
        "4. Preserve all timestamp links\n"
        "5. Return only the Markdown document. Do not wrap it in a code block.\n"
    )
    assert messages[1]["content"] == (
        "Please integrate the following note drafts:\n\nA\n\n---\n\nB"
    )


def test_merge_prompt_snapshot_zh() -> None:
    messages = _build_merge_messages(["甲", "乙"], None, "zh-CN")
    assert messages[0]["content"] == (
        "你是一位笔记整合助手。下面是同一视频的多段笔记草稿，按时间顺序拼接。"
        "请整合为一篇连贯的 Markdown 笔记：\n"
        "1. 统一标题层级（## 用于大主题，### 用于子主题）\n"
        "2. 去除重复内容\n"
        "3. 在顶部添加简要总览\n"
        "4. 保留所有时间戳链接\n"
        "5. 只返回 Markdown 文档本身，不要包裹在代码块中。\n"
    )
    assert messages[1]["content"] == "请整合以下多段笔记草稿：\n\n甲\n\n---\n\n乙"
