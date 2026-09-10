"""Day 1 usage-recording contract.

Implement this module by following assignments/W02_Day1_Assignment_LOCAL.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CallRecord(BaseModel):
    """One model-call attempt.

    Add the exact fields and types specified by the Day 1 assignment.
    """

    pass


def compute_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Return the configured provider charge for one model call."""
    raise NotImplementedError


def append_record(record: CallRecord, run_id: str) -> None:
    """Append one JSON record to runs/{run_id}.jsonl without rewriting the file."""
    raise NotImplementedError
