import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# API Keys
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# LLM Configuration
LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")

# Redis
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

# Upload
UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", "/tmp/videonote_uploads"))
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))

# Ensure upload directory exists
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
