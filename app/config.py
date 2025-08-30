from __future__ import annotations

import os
from dotenv import load_dotenv
from pydantic import BaseModel

# Ladda .env filen
load_dotenv()

class Settings(BaseModel):
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    realtime_url: str = os.getenv("REALTIME_URL", "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17")
    transcribe_model: str = os.getenv("REALTIME_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    input_language: str = os.getenv("INPUT_LANGUAGE", "sv")
    commit_interval_ms: int = int(os.getenv("COMMIT_INTERVAL_MS", "500"))
    add_beta_header: bool = os.getenv("OPENAI_ADD_BETA_HEADER", "1") not in ("0", "", "false", "False")
    cors_origins: str = os.getenv(
        "CORS_ORIGINS",
        "*.lovable.app,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173",
    )
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

settings = Settings()
