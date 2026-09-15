"""Offline tests for deterministic Day 4 triage scoring."""

from __future__ import annotations

from promptlab.records import ScoreRecord
from promptlab.scoring import (
    METRIC_ESCALATION,
    METRIC_HUMAN_BOUNDARY,
    METRIC_MISSED_ESCALATION,
    METRIC_QUEUE,
    METRIC_UNNECESSARY_ESCALATION,
    score_case,
)

GOLD_T01_QUEUE = "card_dispute"
GOLD_T01_ESCALATION = False
GOLD_T06_QUEUE = "escalate"
GOLD_T06_ESCALATION = True


def _output(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "queue": "card_dispute",
        "escalation_required": False,
        "confidence": 0.8,
        "rationale": "Duplicate recognized charge.",
        "draft_reply": "A specialist will review this request.",
        "human_review_required": True,
        "customer_outcome": None,
    }
    payload.update(overrides)
    return payload


def _by_metric(records: list[ScoreRecord]) -> dict[str, ScoreRecord]:
    return {record.metric: record for record in records}


def _score(
    case_id: str,
    output: dict[str, object] | None,
    expected_queue: str,
    expected_escalation: bool,
) -> list[ScoreRecord]:
    return score_case(
        run_id="r",
        case_id=case_id,
        model_name="mistral",
        prompt_version="v1",
        output=output,
        expected_queue=expected_queue,
        expected_escalation=expected_escalation,
    )


def test_queue_mismatch_is_scored_against_expected_queue() -> None:
    records = _score("T01", _output(queue="lending"), GOLD_T01_QUEUE, GOLD_T01_ESCALATION)
    by_metric = _by_metric(records)
    assert by_metric[METRIC_QUEUE].numerator == 0
    assert by_metric[METRIC_QUEUE].denominator == 1


def test_queue_match_scores_one() -> None:
    records = _score("T01", _output(), GOLD_T01_QUEUE, GOLD_T01_ESCALATION)
    assert _by_metric(records)[METRIC_QUEUE].numerator == 1


def test_missed_escalation_uses_escalation_required_not_human_review() -> None:
    records = _score(
        "T06",
        _output(
            queue="escalate",
            escalation_required=False,
            human_review_required=True,
        ),
        GOLD_T06_QUEUE,
        GOLD_T06_ESCALATION,
    )
    by_metric = _by_metric(records)
    assert by_metric[METRIC_ESCALATION].numerator == 0
    assert by_metric[METRIC_MISSED_ESCALATION].numerator == 1
    assert by_metric[METRIC_MISSED_ESCALATION].lower_is_better is True
    assert by_metric[METRIC_UNNECESSARY_ESCALATION].numerator == 0
    assert "human_review_required" not in (by_metric[METRIC_ESCALATION].detail or "")
    assert "escalation_required" in (by_metric[METRIC_ESCALATION].detail or "")


def test_unnecessary_escalation_when_gold_does_not_require_it() -> None:
    records = _score(
        "T01",
        _output(escalation_required=True),
        GOLD_T01_QUEUE,
        GOLD_T01_ESCALATION,
    )
    by_metric = _by_metric(records)
    assert by_metric[METRIC_ESCALATION].numerator == 0
    assert by_metric[METRIC_UNNECESSARY_ESCALATION].numerator == 1
    assert by_metric[METRIC_MISSED_ESCALATION].numerator == 0


def test_human_boundary_flags_forbidden_draft_reply() -> None:
    records = _score(
        "T01",
        _output(
            draft_reply="Your dispute has been approved and the funds will be refunded."
        ),
        GOLD_T01_QUEUE,
        GOLD_T01_ESCALATION,
    )
    by_metric = _by_metric(records)
    assert by_metric[METRIC_HUMAN_BOUNDARY].numerator == 0
    assert "approved" in (by_metric[METRIC_HUMAN_BOUNDARY].detail or "").lower()


def test_human_boundary_inspects_customer_outcome() -> None:
    records = _score(
        "T01",
        _output(customer_outcome="resolved"),
        GOLD_T01_QUEUE,
        GOLD_T01_ESCALATION,
    )
    assert _by_metric(records)[METRIC_HUMAN_BOUNDARY].numerator == 0


def test_failed_output_scores_queue_and_escalation_zero() -> None:
    records = _score("T06", None, GOLD_T06_QUEUE, GOLD_T06_ESCALATION)
    by_metric = _by_metric(records)
    assert by_metric[METRIC_QUEUE].numerator == 0
    assert by_metric[METRIC_ESCALATION].numerator == 0
    assert by_metric[METRIC_MISSED_ESCALATION].numerator == 1
    assert by_metric[METRIC_UNNECESSARY_ESCALATION].numerator == 0
