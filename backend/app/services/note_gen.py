"""LLM-based note generation from transcript text."""

import logging

from openai import OpenAI

from app.config import LLM_API_BASE, LLM_MODEL, OPENAI_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
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
)


def generate_notes(transcript: str, video_title: str | None = None) -> str:
    """Generate structured Markdown notes from a transcript using LLM.

    Args:
        transcript: The transcript text, optionally with timestamps.
        video_title: Optional video title to include in the notes.

    Returns:
        Markdown-formatted notes.
    """
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=LLM_API_BASE)

    title_context = f"\n\nVideo title: {video_title}" if video_title else ""

    user_content = (
        "Please generate structured Markdown notes from the "
        f"following video transcript.{title_context}\n\n"
        f"Transcript:\n{transcript}"
    )

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    notes = response.choices[0].message.content
    return notes or ""
