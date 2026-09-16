"""Case and gold-label loading for the Day 5 harness."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from promptlab.config import PROJECT_ROOT
from promptlab.schemas import TaskName

TASKS: tuple[TaskName, ...] = ("triage", "summarization", "extraction")


class GoldLabel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    task: TaskName
    expected_status: str | None = None
    recoverable_fields: list[str] = Field(default_factory=list)
    expected_queue: str | None = None
    expected_escalation: bool | None = None
    version_group: str | None = None
    expected_current_case_id: str | None = None
    as_of: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class Case:
    id: str
    task: TaskName
    source: str


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_gold(task: TaskName) -> dict[str, GoldLabel]:
    path = PROJECT_ROOT / "cases" / "gold" / f"{task}.jsonl"
    return {row["id"]: GoldLabel.model_validate(row) for row in _read_jsonl(path)}


def load_cases(task: TaskName) -> list[tuple[Case, GoldLabel]]:
    cases_path = PROJECT_ROOT / "cases" / f"{task}.jsonl"
    gold = load_gold(task)
    pairs: list[tuple[Case, GoldLabel]] = []
    for row in _read_jsonl(cases_path):
        case_id = str(row["id"])
        pairs.append(
            (
                Case(id=case_id, task=task, source=str(row["source"])),
                gold[case_id],
            )
        )
    return pairs


def validate_corpus() -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in TASKS:
        pairs = load_cases(task)
        if len(pairs) != 12:
            raise ValueError(f"{task} corpus must contain 12 cases, found {len(pairs)}")
        counts[task] = len(pairs)
    return counts
