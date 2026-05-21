import os
import secrets
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
YT_DLP_COOKIES_FROM_BROWSER: str = os.getenv("YT_DLP_COOKIES_FROM_BROWSER", "")
YT_DLP_COOKIES_FILE: str = os.getenv("YT_DLP_COOKIES_FILE", "")

# Upload
UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", "/tmp/videonote_uploads"))
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))

# Auth
SECRET_KEY: str = os.getenv("SECRET_KEY", "") or secrets.token_urlsafe(32)
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Ensure upload directory exists
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Preset provider/model lists for frontend selection
PROVIDER_PRESETS: dict = {
    "asr": [
        {
            "provider": "openai",
            "models": ["whisper-1"],
            "api_base": "https://api.openai.com/v1",
        },
        {
            "provider": "siliconflow",
            "models": ["FunAudioLLM/SenseVoiceSmall"],
            "api_base": "https://api.siliconflow.cn/v1",
        },
    ],
    "llm": [
        {
            "provider": "openai",
            "models": ["gpt-4o", "gpt-4o-mini"],
            "api_base": "https://api.openai.com/v1",
        },
        {
            "provider": "deepseek",
            "models": ["deepseek-chat", "deepseek-reasoner"],
            "api_base": "https://api.deepseek.com/v1",
        },
    ],
}
