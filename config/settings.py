"""Central configuration. Values can be overridden through the .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    # LLM
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

    # Clarification engine: ask the user only when confidence is below this value
    clarification_threshold: float = 0.75
    max_clarification_questions: int = 3

    # SQL pipeline
    max_sql_retries: int = 2                      # self-repair attempts after the first try
    max_result_rows: int = int(os.getenv("MAX_RESULT_ROWS", "1000"))
    query_timeout_seconds: float = 10.0
    max_history_turns: int = 3                    # previous Q&A turns given to the LLM

    # Uploads
    upload_dir: Path = BASE_DIR / "uploads"
    max_upload_mb: int = 50
    allowed_extensions: tuple = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json")


settings = Settings()
