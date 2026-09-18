from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = PROJECT_ROOT / "policy.md"
MIGRATION_PATH = PROJECT_ROOT / "migrations" / "001_init.sql"

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    ollama_host: str
    embed_model: str
    chat_model: str
    embed_dim: int
    policy_path: Path
    migration_path: Path


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://rag:rag@localhost:5432/expense_policy",
        ),
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
        embed_model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
        chat_model=os.getenv("CHAT_MODEL", "mistral"),
        embed_dim=int(os.getenv("EMBED_DIM", "768")),
        policy_path=Path(os.getenv("POLICY_PATH", POLICY_PATH)),
        migration_path=Path(os.getenv("MIGRATION_PATH", MIGRATION_PATH)),
    )
