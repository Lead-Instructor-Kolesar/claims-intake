"""Day 1 usage-recording contract.

Implement this module by following assignments/W02_Day1_Assignment_LOCAL.md.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from promptlab.config import Settings
from promptlab.errors import UnknownModelError


class CallRecord(BaseModel):
    """One model-call attempt.

    Add the exact fields and types specified by the Day 1 assignment.
    """

    record_id: str
    run_id: str
    timestamp: datetime
    provider: Literal["ollama"]
    model_id: str
    task: Literal["triage", "summarization", "extraction"]
    case_id: str
    prompt_id: str
    prompt_version: str
    attempt: int
    temperature: float
    max_output_tokens: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int | None
    latency_ms: int
    cost_usd: float
    stop_reason: str | None
    error_type: str | None
    response_text: str | None


def compute_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Return the configured provider charge for one model call."""
    for config in Settings.from_env().models.values():
        if config.model_id == model_id:
            return float(config.cost(input_tokens, output_tokens))
    raise UnknownModelError(model_id)


def append_record(record: CallRecord, run_id: str) -> None:
    """Append one JSON record to runs/{run_id}.jsonl without rewriting the file."""
    path = Path("runs") / f"{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json() + "\n")
