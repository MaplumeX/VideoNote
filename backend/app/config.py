import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# API Keys
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ASR Configuration (fallback to OPENAI_API_KEY / OpenAI defaults)
ASR_PROVIDER: str = os.getenv("ASR_PROVIDER", "openai")
ASR_API_KEY: str = os.getenv("ASR_API_KEY", "") or OPENAI_API_KEY
ASR_API_BASE: str = os.getenv("ASR_API_BASE", "https://api.openai.com/v1")
ASR_MODEL: str = os.getenv("ASR_MODEL", "whisper-1")

# LLM Configuration (fallback to OPENAI_API_KEY / OpenAI defaults)
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "") or OPENAI_API_KEY
LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")

# yt-dlp proxy (e.g. "http://127.0.0.1:7890")
YT_DLP_PROXY: str = os.getenv("YT_DLP_PROXY", "")

# Upload
UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", "/tmp/videonote_uploads"))
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))

# Ensure upload directory exists
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
