"""Call records. Week 2 reference implementation, contract C1 of that week.

The authoritative fields are the token counts. Cost is derived from them and
stored for convenience, so that if a rate turns out to be wrong every record can
be recomputed from what it already holds.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from promptlab.errors import UnknownModelError


class CallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    timestamp: datetime
    provider: Literal["anthropic", "azure_openai"]
    model_id: str
    task: Literal["triage", "summarize", "extract"]
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


def compute_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    rates: dict[str, dict[str, float]],
) -> float:
    """Derive cost from token counts and the rate table."""
    if model_id not in rates:
        raise UnknownModelError(model_id)
    rate = rates[model_id]
    return (input_tokens * rate["input"] + output_tokens * rate["output"]) / 1_000_000


def append_record(record: CallRecord, run_id: str, run_dir: Path) -> None:
    """Append one serialized record per line to run_dir/{run_id}.jsonl.

    A run file is never rewritten and never has a line edited.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{run_id}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(json.loads(record.model_dump_json())) + "\n")
