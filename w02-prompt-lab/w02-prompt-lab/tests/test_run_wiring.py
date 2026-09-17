"""Wiring tests for the Day 5 runner glue. No model calls."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from promptlab.corpus import Case, GoldLabel
from promptlab.records import OutputRecord, ScoreRecord
from promptlab.report import write_reports
from promptlab.run import (
    TASK_SPECS,
    _score_task_model,
    _usage_records,
    _version_selection_scores,
)
from promptlab.usage import CallRecord


def call_record(**overrides: Any) -> CallRecord:
    values: dict[str, Any] = dict(
        record_id="c1",
        run_id="r",
        timestamp=datetime.now(UTC),
        provider="ollama",
        model_id="mistral:7b",
        task="triage",
        case_id="T01",
        prompt_id="triage",
        prompt_version="v2",
        attempt=1,
        temperature=0.0,
        max_output_tokens=1024,
        input_tokens=100,
        output_tokens=20,
        cached_input_tokens=None,
        latency_ms=500,
        cost_usd=0.0,
        stop_reason="stop",
        error_type=None,
        response_text=None,
    )
    values.update(overrides)
    return CallRecord.model_validate(values)


def output_record(**overrides: Any) -> OutputRecord:
    values: dict[str, Any] = dict(
        run_id="r",
        task="triage",
        case_id="T01",
        model_name="mistral",
        model_id="mistral:7b",
        prompt_id="triage",
        prompt_version="v2",
        succeeded=True,
        repairs=0,
        output=None,
        error=None,
    )
    values.update(overrides)
    return OutputRecord(**values)


def test_usage_records_distinguish_repair_from_retry() -> None:
    calls = [
        call_record(),
        call_record(record_id="c2", attempt=2),
        call_record(record_id="c3"),
    ]
    usage = _usage_records(calls, {"c3"}, {"mistral:7b": "mistral"})
    assert [row.kind for row in usage] == ["primary", "transport_retry", "repair"]
    assert usage[0].model_name == "mistral"
    assert usage[0].prompt_id == "triage"
    assert usage[0].cost_usd == Decimal("0.0")


def test_triage_scoring_emits_queue_and_pii() -> None:
    spec = TASK_SPECS["triage"]
    record = output_record(
        output={
            "queue": "escalate",
            "escalation_required": True,
            "confidence": 0.9,
            "rationale": "mixed signals",
            "draft_reply": "We will review. Contact us at a@b.com.",
            "human_review_required": True,
            "customer_outcome": None,
        }
    )
    scores = _score_task_model(
        run_id="r",
        spec=spec,
        outputs=[record],
        pairs=[
            (
                Case(id="T01", task="triage", document_text="msg"),
                GoldLabel(
                    id="T01", task="triage", expected_queue="escalate",
                    expected_escalation=True,
                ),
            )
        ],
        source_by_id={"T01": "doc"},
    )
    by_metric = {score.metric: score for score in scores}
    assert by_metric["queue"].numerator == 1
    assert by_metric["escalation"].numerator == 1
    assert by_metric["pii_leakage"].numerator == 1
    assert "a@b.com" in (by_metric["pii_leakage"].detail or "")


def test_version_selection_uses_the_deterministic_rule() -> None:
    spec = TASK_SPECS["extraction"]

    def gold(id: str) -> GoldLabel:
        return GoldLabel.model_validate(
            {
                "id": id,
                "task": "extraction",
                "version_group": "g",
                "as_of": "2025-06-01",
                "expected_current_case_id": "E02",
            }
        )

    pairs = [
        (Case(id="E01", task="extraction", document_text="doc"), gold("E01")),
        (Case(id="E02", task="extraction", document_text="doc2"), gold("E02")),
    ]
    outputs = [
        output_record(
            task="extraction", case_id="E01", prompt_id="extract",
            output={
                "version": {"value": "1.0", "status": "present", "citation": None},
                "effective_date": {
                    "value": "2025-01-01", "status": "present", "citation": None,
                },
            },
        ),
        output_record(
            task="extraction", case_id="E02", prompt_id="extract",
            output={
                "version": {"value": "2.0", "status": "present", "citation": None},
                "effective_date": {
                    "value": "2025-05-01", "status": "present", "citation": None,
                },
            },
        ),
    ]
    scores = _version_selection_scores(
        run_id="r", spec=spec, model_name="mistral", outputs=outputs, pairs=pairs
    )
    assert len(scores) == 1
    assert scores[0].case_id == "VG:g"
    assert (scores[0].numerator, scores[0].denominator) == (1, 1)


def test_reports_render_from_projected_records(tmp_path: Path) -> None:
    usage = _usage_records([call_record()], set(), {"mistral:7b": "mistral"})
    outputs = [
        output_record(
            output={
                "queue": "escalate",
                "escalation_required": True,
                "confidence": 0.9,
                "rationale": "mixed",
                "draft_reply": "We will review.",
                "human_review_required": True,
                "customer_outcome": None,
            }
        )
    ]
    scores = [
        ScoreRecord(
            run_id="r",
            task="triage",
            case_id="T01",
            model_name="mistral",
            prompt_id="triage",
            prompt_version="v2",
            scorer_version="day5.v1",
            metric="queue",
            numerator=1,
            denominator=1,
        )
    ]
    report = tmp_path / "comparison.md"
    decision = tmp_path / "model-decision.md"
    write_reports(
        run_id="r",
        models=["mistral"],
        usage=usage,
        outputs=outputs,
        scores=scores,
        report_path=report,
        decision_path=decision,
    )
    text = report.read_text(encoding="utf-8")
    assert "v2" in text and "1/1" in text
    assert "mistral" in decision.read_text(encoding="utf-8")
