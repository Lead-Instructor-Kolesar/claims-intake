from __future__ import annotations

import os
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PII_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{8,12}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\+1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)"),
)


@dataclass(frozen=True)
class ModelConfig:
    logical_name: str
    model_id: str
    input_usd_per_million: Decimal = Decimal("0")
    output_usd_per_million: Decimal = Decimal("0")

    def cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        million = Decimal(1_000_000)
        return (
            Decimal(prompt_tokens) * self.input_usd_per_million / million
            + Decimal(completion_tokens) * self.output_usd_per_million / million
        )


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    models: dict[str, ModelConfig]
    temperature: float
    max_retries: int
    max_schema_repairs: int
    per_run_cap_usd: Decimal
    weekly_cap_usd: Decimal

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(PROJECT_ROOT / ".env")
        model_a = os.getenv("MODEL_A", "mistral:7b")
        model_b = os.getenv("MODEL_B", "qwen3:8b")
        return cls(
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
            ).rstrip("/"),
            models={
                "mistral": ModelConfig(logical_name="mistral", model_id=model_a),
                "qwen": ModelConfig(logical_name="qwen", model_id=model_b),
            },
            temperature=float(os.getenv("TEMPERATURE", "0.0")),
            max_retries=int(os.getenv("MAX_RETRIES", "2")),
            max_schema_repairs=int(os.getenv("MAX_SCHEMA_REPAIRS", "1")),
            per_run_cap_usd=Decimal(os.getenv("PER_RUN_CAP_USD", "2.00")),
            weekly_cap_usd=Decimal(os.getenv("WEEKLY_CAP_USD", "25.00")),
        )

