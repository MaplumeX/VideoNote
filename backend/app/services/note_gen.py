"""LLM-based note generation from transcript text."""

import logging
import time

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from app.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL
from app.services.markdown import normalize_note_markdown

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_CHARS = 60000

_PROMPTS_WITH_TIMESTAMPS: dict[str, dict[str, str]] = {
    "en": {
        "system": (
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
        ),
        "user": "Please generate structured Markdown notes from the following video transcript.",
    },
    "zh-CN": {
        "system": (
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
        ),
        "user": "请根据以下视频转录文本生成结构化的 Markdown 笔记。",
    },
}

_PROMPTS_WITHOUT_TIMESTAMPS: dict[str, dict[str, str]] = {
    "en": {
        "system": (
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
        ),
        "user": "Please generate structured Markdown notes from the following video transcript.",
    },
    "zh-CN": {
        "system": (
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
        ),
        "user": "请根据以下视频转录文本生成结构化的 Markdown 笔记。",
    },
}


def _is_retryable(exc: Exception) -> bool:
    """Return True if the LLM exception is worth retrying."""
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500
    return False


def _call_llm(
    client: OpenAI,
    messages: list[dict[str, str]],
    model: str,
    temperature: float = 0.3,
    max_tokens: int = 8192,
) -> str:
    """Call LLM with exponential-backoff retry for transient failures."""
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt + 1 >= max_attempts or not _is_retryable(e):
                raise
            wait = 2 ** (attempt + 1)  # 2s, 4s
            logger.warning(
                f"LLM call attempt {attempt + 1} failed, retrying in {wait}s: {e}"
            )
            time.sleep(wait)
    return ""  # unreachable


def _split_transcript(transcript: str, max_chars: int = MAX_TRANSCRIPT_CHARS) -> list[str]:
    """Split transcript at line boundaries, each chunk <= max_chars.

    If a single line exceeds max_chars it is kept as-is (cannot split further
    without breaking a timestamp entry).
    """
    if len(transcript) <= max_chars:
        return [transcript]
    lines = transcript.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1  # +1 for the \n we'll rejoin with
        if current_len + line_len > max_chars and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def _generate_notes_single(
    transcript: str,
    video_title: str | None,
    language: str,
    api_key: str,
    api_base: str,
    model: str,
    has_timestamps: bool,
) -> str:
    """Generate notes for a single transcript chunk (no truncation, no normalize)."""
    client = OpenAI(api_key=api_key, base_url=api_base)

    prompts_map = _PROMPTS_WITH_TIMESTAMPS if has_timestamps else _PROMPTS_WITHOUT_TIMESTAMPS
    prompts = prompts_map.get(language, prompts_map["en"])

    if video_title:
        title_context = (
            f"\n\nVideo title: {video_title}"
            if language == "en"
            else f"\n\n视频标题：{video_title}"
        )
    else:
        title_context = ""

    transcript_label = "转录文本" if language == "zh-CN" else "Transcript"
    user_content = f"{prompts['user']}{title_context}\n\n{transcript_label}:\n{transcript}"

    return _call_llm(
        client,
        [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": user_content},
        ],
        model,
    ) or ""


def _merge_notes(
    sub_notes: list[str],
    video_title: str | None,
    language: str,
    api_key: str,
    api_base: str,
    model: str,
) -> str:
    """Merge sub-notes by unifying heading hierarchy and adding an overview."""
    client = OpenAI(api_key=api_key, base_url=api_base)

    if language == "zh-CN":
        system = (
            "你是一位笔记整合助手。下面是同一视频的多段笔记草稿，按时间顺序拼接。"
            "请整合为一篇连贯的 Markdown 笔记：\n"
            "1. 统一标题层级（## 用于大主题，### 用于子主题）\n"
            "2. 去除重复内容\n"
            "3. 在顶部添加简要总览\n"
            "4. 保留所有时间戳链接\n"
            "5. 只返回 Markdown 文档本身，不要包裹在代码块中。\n"
        )
        user_prefix = "请整合以下多段笔记草稿："
    else:
        system = (
            "You are a note integration assistant. Below are multiple note drafts "
            "from the same video, concatenated in order. "
            "Merge them into a single coherent Markdown note:\n"
            "1. Unify heading hierarchy (## for major topics, ### for subtopics)\n"
            "2. Remove duplicates\n"
            "3. Add a brief overview at the top\n"
            "4. Preserve all timestamp links\n"
            "5. Return only the Markdown document. Do not wrap it in a code block.\n"
        )
        user_prefix = "Please integrate the following note drafts:"

    combined = "\n\n---\n\n".join(sub_notes)
    user_content = f"{user_prefix}\n\n{combined}"

    return _call_llm(
        client,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        model,
        temperature=0.3,
    ) or ""


def generate_notes(
    transcript: str,
    video_title: str | None = None,
    language: str = "en",
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
    has_timestamps: bool = True,
) -> str:
    """Generate structured Markdown notes from a transcript using LLM.

    For transcripts exceeding ``MAX_TRANSCRIPT_CHARS`` the text is split at
    line boundaries into multiple chunks.  Each chunk is sent to the LLM
    independently, then the resulting sub-notes are merged with a final LLM
    call that unifies heading hierarchy and adds an overview.

    Args:
        transcript: The transcript text, optionally with timestamps.
        video_title: Optional video title to include in the notes.
        language: Language code for prompt selection ("en" or "zh-CN").
        api_key: Optional runtime API key (overrides config default).
        api_base: Optional runtime API base URL (overrides config default).
        model: Optional runtime model name (overrides config default).
        has_timestamps: Whether the transcript contains timestamps.
            When False, the prompt instructs the LLM not to add timestamps.

    Returns:
        Markdown-formatted notes.
    """
    _api_key = api_key or LLM_API_KEY
    _api_base = api_base or LLM_API_BASE
    _model = model or LLM_MODEL

    chunks = _split_transcript(transcript)

    if len(chunks) == 1:
        notes = _generate_notes_single(
            chunks[0],
            video_title,
            language,
            _api_key,
            _api_base,
            _model,
            has_timestamps,
        )
        return normalize_note_markdown(notes)

    # Multi-chunk: generate sub-notes per chunk, then merge.
    sub_notes: list[str] = []
    for i, chunk in enumerate(chunks):
        logger.info(f"Generating notes for chunk {i + 1}/{len(chunks)}")
        sub_notes.append(
            _generate_notes_single(
                chunk,
                video_title,
                language,
                _api_key,
                _api_base,
                _model,
                has_timestamps,
            )
        )

    merged = _merge_notes(sub_notes, video_title, language, _api_key, _api_base, _model)
    return normalize_note_markdown(merged)