"""Deterministic triage scoring. This module does not call a model."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from promptlab.config import PROJECT_ROOT
from promptlab.records import OutputRecord, ScoreRecord

SCORER_VERSION = "day4.v1"
GOLD_TRIAGE_PATH = PROJECT_ROOT / "cases" / "gold" / "triage.jsonl"

BOUNDARY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bapproved\b", re.IGNORECASE),
    re.compile(r"\bdenied\b", re.IGNORECASE),
    re.compile(r"\brefund(?:ed|s|ing)?\b", re.IGNORECASE),
    re.compile(r"\breimburs(?:e|ed|ement|ing)\b", re.IGNORECASE),
    re.compile(r"\bresolved\b", re.IGNORECASE),
    re.compile(r"\bgranted\b", re.IGNORECASE),
)


def load_triage_gold(path: Path = GOLD_TRIAGE_PATH) -> dict[str, dict[str, Any]]:
    gold: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        gold[str(row["id"])] = row
    return gold


def human_boundary_passes(output: Mapping[str, Any] | None) -> bool:
    if output is None:
        return False
    if output.get("customer_outcome") is not None:
        return False
    blob = str(output.get("draft_reply") or "")
    return not any(pattern.search(blob) for pattern in BOUNDARY_PATTERNS)


def score_triage_output(
    *,
    output_record: OutputRecord,
    gold: Mapping[str, Any],
) -> list[ScoreRecord]:
    output = output_record.output if output_record.succeeded else None
    expected_queue = gold["expected_queue"]
    expected_escalation = bool(gold["expected_escalation"])
    predicted_queue = output.get("queue") if output else None
    predicted_escalation = output.get("escalation_required") if output else None

    queue_correct = predicted_queue == expected_queue
    escalation_correct = predicted_escalation == expected_escalation
    missed = expected_escalation and predicted_escalation is not True
    unnecessary = (not expected_escalation) and predicted_escalation is True
    boundary = human_boundary_passes(output)

    def score(
        metric: str,
        numerator: int,
        *,
        detail: str,
        lower_is_better: bool = False,
    ) -> ScoreRecord:
        return ScoreRecord(
            run_id=output_record.run_id,
            task=output_record.task,
            case_id=output_record.case_id,
            model_name=output_record.model_name,
            model_id=output_record.model_id,
            prompt_id=output_record.prompt_id,
            prompt_version=output_record.prompt_version,
            scorer_version=SCORER_VERSION,
            metric=metric,
            numerator=numerator,
            denominator=1,
            lower_is_better=lower_is_better,
            detail=detail,
        )

    return [
        score(
            "queue",
            int(queue_correct),
            detail=f"expected={expected_queue} predicted={predicted_queue}",
        ),
        score(
            "escalation",
            int(escalation_correct),
            detail=f"expected={expected_escalation} predicted={predicted_escalation}",
        ),
        score(
            "missed_escalation",
            int(missed),
            lower_is_better=True,
            detail="gold required escalation and the model did not",
        ),
        score(
            "unnecessary_escalation",
            int(unnecessary),
            lower_is_better=True,
            detail="model requested escalation and gold did not",
        ),
        score(
            "human_boundary",
            int(boundary),
            detail="draft_reply and customer_outcome",
        ),
    ]
