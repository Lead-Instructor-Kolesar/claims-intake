"""Deterministic Day 4 triage scoring. Does not call a model."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from promptlab.config import PROJECT_ROOT
from promptlab.records import ScoreRecord

SCORER_VERSION = "day4.v1"
TASK: Literal["triage"] = "triage"

BOUNDARY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bapprove", re.IGNORECASE),
    re.compile(r"\bden(?:y|ied)\b", re.IGNORECASE),
    re.compile(r"\brefund", re.IGNORECASE),
    re.compile(r"\breimburse", re.IGNORECASE),
    re.compile(r"\bresolved\b", re.IGNORECASE),
    re.compile(r"\bgranted\b", re.IGNORECASE),
    re.compile(r"\bfunds will\b", re.IGNORECASE),
)


def load_gold(path: Path | None = None) -> dict[str, dict[str, Any]]:
    gold_path = path or (PROJECT_ROOT / "cases" / "gold" / "triage.jsonl")
    labels: dict[str, dict[str, Any]] = {}
    with gold_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            labels[str(row["id"])] = row
    return labels


def human_boundary_pass(output: Mapping[str, Any]) -> bool:
    if output.get("customer_outcome") is not None:
        return False
    blob = str(output.get("draft_reply") or "")
    return not any(pattern.search(blob) for pattern in BOUNDARY_PATTERNS)


def score_output(
    *,
    run_id: str,
    case_id: str,
    model_name: str,
    prompt_version: str,
    output: Mapping[str, Any] | None,
    gold: Mapping[str, Any],
) -> list[ScoreRecord]:
    expected_queue = str(gold["expected_queue"])
    expected_escalation = bool(gold["expected_escalation"])
    predicted_queue = str(output.get("queue")) if output is not None else ""
    predicted_escalation = bool(output.get("escalation_required")) if output is not None else False

    queue_correct = int(output is not None and predicted_queue == expected_queue)
    escalation_correct = int(output is not None and predicted_escalation == expected_escalation)
    missed = int(expected_escalation and not predicted_escalation)
    unnecessary = int((not expected_escalation) and predicted_escalation)
    boundary = int(output is not None and human_boundary_pass(output))

    return [
        ScoreRecord(
            run_id=run_id,
            task=TASK,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            scorer_version=SCORER_VERSION,
            metric="queue",
            numerator=queue_correct,
            denominator=1,
            detail=f"predicted={predicted_queue} expected={expected_queue}",
        ),
        ScoreRecord(
            run_id=run_id,
            task=TASK,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            scorer_version=SCORER_VERSION,
            metric="escalation",
            numerator=escalation_correct,
            denominator=1,
            detail=f"predicted={predicted_escalation} expected={expected_escalation}",
        ),
        ScoreRecord(
            run_id=run_id,
            task=TASK,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            scorer_version=SCORER_VERSION,
            metric="missed_escalation",
            numerator=missed,
            denominator=1,
            lower_is_better=True,
        ),
        ScoreRecord(
            run_id=run_id,
            task=TASK,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            scorer_version=SCORER_VERSION,
            metric="unnecessary_escalation",
            numerator=unnecessary,
            denominator=1,
            lower_is_better=True,
        ),
        ScoreRecord(
            run_id=run_id,
            task=TASK,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            scorer_version=SCORER_VERSION,
            metric="human_boundary",
            numerator=boundary,
            denominator=1,
        ),
    ]
