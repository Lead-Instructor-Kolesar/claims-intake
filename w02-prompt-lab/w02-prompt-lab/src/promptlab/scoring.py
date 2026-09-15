"""Deterministic Day 4 triage scoring. No model calls.

Scores the existing TriageOutput fields against gold labels using the
repository ScoreRecord contract. Escalation is always compared through
``escalation_required`` and gold ``expected_escalation``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from promptlab.records import ScoreRecord

SCORER_VERSION = "day4.v1"

METRIC_QUEUE = "queue"
METRIC_ESCALATION = "escalation"
METRIC_MISSED_ESCALATION = "missed_escalation"
METRIC_UNNECESSARY_ESCALATION = "unnecessary_escalation"
METRIC_HUMAN_BOUNDARY = "human_boundary"

# config.py ships PII_PATTERNS only, not boundary language. These patterns are
# the deterministic human-boundary check for draft_reply and customer_outcome.
_BOUNDARY_LANGUAGE = re.compile(
    r"\b("
    r"approved|approval|"
    r"refund(?:ed|s)?|"
    r"reimburs(?:e|ed|ement)|"
    r"denied|denial|"
    r"resolved|resolution|"
    r"granted"
    r")\b",
    re.IGNORECASE,
)


def _unit(passed: bool) -> tuple[int, int]:
    return (1 if passed else 0, 1)


def _predicted_escalation(output: Mapping[str, Any] | None) -> bool | None:
    """Return the model's escalation_required value, or None if it is absent."""
    if output is None:
        return None
    value = output.get("escalation_required")
    if isinstance(value, bool):
        return value
    return None


def _boundary_corpus(output: Mapping[str, Any] | None) -> str:
    if output is None:
        return ""
    parts: list[str] = []
    draft_reply = output.get("draft_reply")
    if isinstance(draft_reply, str):
        parts.append(draft_reply)
    customer_outcome = output.get("customer_outcome")
    if customer_outcome is not None:
        parts.append(str(customer_outcome))
    return "\n".join(parts)


def _boundary_hits(text: str) -> list[str]:
    return [match.group(0) for match in _BOUNDARY_LANGUAGE.finditer(text)]


def score_case(
    *,
    run_id: str,
    case_id: str,
    model_name: str,
    prompt_version: str,
    output: Mapping[str, Any] | None,
    expected_queue: str,
    expected_escalation: bool,
) -> list[ScoreRecord]:
    """Score one triage case against gold queue and expected_escalation."""
    predicted_queue = None if output is None else output.get("queue")
    queue_ok = predicted_queue == expected_queue

    predicted_escalation = _predicted_escalation(output)
    escalation_ok = predicted_escalation is expected_escalation
    missed = expected_escalation and predicted_escalation is not True
    unnecessary = (not expected_escalation) and predicted_escalation is True

    hits = _boundary_hits(_boundary_corpus(output))
    boundary_ok = not hits

    def record(
        metric: str,
        numerator: int,
        *,
        lower_is_better: bool = False,
        detail: str | None = None,
    ) -> ScoreRecord:
        return ScoreRecord(
            run_id=run_id,
            task="triage",
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

    queue_num, _ = _unit(queue_ok)
    escalation_num, _ = _unit(escalation_ok)
    missed_num, _ = _unit(missed)
    unnecessary_num, _ = _unit(unnecessary)
    boundary_num, _ = _unit(boundary_ok)

    return [
        record(
            METRIC_QUEUE,
            queue_num,
            detail=(
                None
                if queue_ok
                else f"predicted={predicted_queue!r} expected={expected_queue!r}"
            ),
        ),
        record(
            METRIC_ESCALATION,
            escalation_num,
            detail=(
                None
                if escalation_ok
                else (
                    f"escalation_required={predicted_escalation!r} "
                    f"expected_escalation={expected_escalation!r}"
                )
            ),
        ),
        record(
            METRIC_MISSED_ESCALATION,
            missed_num,
            lower_is_better=True,
            detail="gold required escalation_required=true; model did not" if missed else None,
        ),
        record(
            METRIC_UNNECESSARY_ESCALATION,
            unnecessary_num,
            lower_is_better=True,
            detail="model set escalation_required=true; gold did not" if unnecessary else None,
        ),
        record(
            METRIC_HUMAN_BOUNDARY,
            boundary_num,
            detail=None if boundary_ok else f"forbidden language: {', '.join(hits)}",
        ),
    ]


def score_outputs(
    outputs: Sequence[Mapping[str, Any]],
    gold_by_id: Mapping[str, Mapping[str, Any]],
) -> list[ScoreRecord]:
    """Score OutputRecord-shaped mappings against gold rows keyed by case id."""
    records: list[ScoreRecord] = []
    for row in outputs:
        case_id = str(row["case_id"])
        gold = gold_by_id[case_id]
        output = row.get("output")
        mapping = output if isinstance(output, Mapping) else None
        records.extend(
            score_case(
                run_id=str(row["run_id"]),
                case_id=case_id,
                model_name=str(row["model_name"]),
                prompt_version=str(row["prompt_version"]),
                output=mapping,
                expected_queue=str(gold["expected_queue"]),
                expected_escalation=bool(gold["expected_escalation"]),
            )
        )
    return records
