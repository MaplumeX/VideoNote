"""LLM-based note generation from transcript text."""

import logging

from openai import OpenAI

from app.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

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
        ),
        "user": "请根据以下视频转录文本生成结构化的 Markdown 笔记。",
    },
}


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
    client = OpenAI(api_key=_api_key, base_url=_api_base)

    prompts_map = _PROMPTS_WITH_TIMESTAMPS if has_timestamps else _PROMPTS_WITHOUT_TIMESTAMPS
    prompts = prompts_map.get(language, prompts_map["en"])

    title_context = (
        f"\n\nVideo title: {video_title}"
        if language == "en" and video_title
        else f"\n\n视频标题：{video_title}"
        if video_title
        else ""
    )

    transcript_label = "转录文本" if language == "zh-CN" else "Transcript"
    user_content = f"{prompts['user']}{title_context}\n\n{transcript_label}:\n{transcript}"

    response = client.chat.completions.create(
        model=_model,
        messages=[
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    notes = response.choices[0].message.content
    return notes or ""
