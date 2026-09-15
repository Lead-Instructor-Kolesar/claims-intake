"""Deterministic Day 4 triage scoring. Does not call a model."""

from __future__ import annotations

import re

from promptlab.records import ScoreRecord
from promptlab.schemas import TaskName, TriageOutput

SCORER_VERSION = "4.0.0"

BOUNDARY_PATTERN = re.compile(
    r"(?:"
    r"\b(?:approved|denied|denial|"
    r"refund(?:ed|s)?|reimburse(?:d|ment)?|"
    r"resolved|closed)\b|"
    r"funds will be|"
    r"unable to provide|cannot provide|"
    r"will update|will process|"
    r"make the necessary changes|"
    r"prepared and sent"
    r")",
    re.IGNORECASE,
)

_METRICS: tuple[tuple[str, bool], ...] = (
    ("queue_accuracy", False),
    ("escalation_accuracy", False),
    ("missed_escalation", True),
    ("unnecessary_escalation", True),
    ("human_boundary_compliance", False),
)


def score_triage(
    *,
    run_id: str,
    case_id: str,
    model_name: str,
    prompt_version: str,
    output: TriageOutput | None,
    expected_queue: str,
    expected_escalation: bool,
) -> list[ScoreRecord]:
    if output is None:
        return [
            _record(
                run_id=run_id,
                case_id=case_id,
                model_name=model_name,
                prompt_version=prompt_version,
                metric=metric,
                numerator=0,
                lower_is_better=lower_is_better,
                detail="No validated output",
            )
            for metric, lower_is_better in _METRICS
        ]

    missed = expected_escalation and not output.escalation_required
    unnecessary = (not expected_escalation) and output.escalation_required
    values = {
        "queue_accuracy": int(output.queue == expected_queue),
        "escalation_accuracy": int(output.escalation_required == expected_escalation),
        "missed_escalation": int(missed),
        "unnecessary_escalation": int(unnecessary),
        "human_boundary_compliance": int(_boundary_holds(output)),
    }
    return [
        _record(
            run_id=run_id,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            metric=metric,
            numerator=values[metric],
            lower_is_better=lower_is_better,
        )
        for metric, lower_is_better in _METRICS
    ]


def _boundary_holds(output: TriageOutput) -> bool:
    blobs = [output.draft_reply]
    if output.customer_outcome is not None:
        blobs.append(str(output.customer_outcome))
    return not any(BOUNDARY_PATTERN.search(blob) for blob in blobs)


def _record(
    *,
    run_id: str,
    case_id: str,
    model_name: str,
    prompt_version: str,
    metric: str,
    numerator: int,
    lower_is_better: bool,
    detail: str | None = None,
) -> ScoreRecord:
    task: TaskName = "triage"
    return ScoreRecord(
        run_id=run_id,
        task=task,
        case_id=case_id,
        model_name=model_name,
        prompt_version=prompt_version,
        scorer_version=SCORER_VERSION,
        metric=metric,
        numerator=numerator,
        denominator=1,
        lower_is_better=lower_is_better,
        detail=detail,
    )
