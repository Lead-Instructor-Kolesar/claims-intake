"""Offline tests for Day 4 prompt loading and notes rendering."""

from __future__ import annotations

from datetime import UTC, datetime

from promptlab.day4 import changed_queue_count, render_notes
from promptlab.prompts import load, render_user
from promptlab.records import OutputRecord, ScoreRecord
from promptlab.scoring import METRIC_QUEUE, SCORER_VERSION
from promptlab.usage import CallRecord


def _output_record(case_id: str, version: str, queue: str) -> OutputRecord:
    return OutputRecord(
        run_id="run",
        task="triage",
        case_id=case_id,
        model_name="mistral",
        model_id="mistral:7b",
        prompt_version=version,
        succeeded=True,
        repairs=0,
        output={
            "queue": queue,
            "escalation_required": False,
            "confidence": 0.5,
            "rationale": "r",
            "draft_reply": "A specialist will review this.",
            "human_review_required": True,
            "customer_outcome": None,
        },
        error=None,
    )


def test_triage_prompts_are_layered_and_v1_omits_analysis() -> None:
    v1 = load("triage", "v1")
    v2 = load("triage", "v2")

    assert v1.system
    assert v2.system
    assert "<customer_message>" in v1.user_template
    assert v1.user_template.count("{document_text}") == 1
    assert "{schema_description}" in v1.system
    assert "analysis" not in v1.system.lower()
    assert "analysis" not in v1.user_template.lower()
    assert "analysis" in v2.system.lower()
    assert "analysis" in v2.user_template.lower()


def test_render_user_fills_customer_fence() -> None:
    template = load("triage", "v1")
    rendered = render_user(template, {}, untrusted="I was charged twice.")
    assert "I was charged twice." in rendered
    assert rendered.count("</customer_message>") == 1


def test_changed_queue_count_detects_one_difference() -> None:
    outputs = [
        _output_record("T01", "v1", "card_dispute"),
        _output_record("T02", "v1", "fraud_report"),
        _output_record("T01", "v2", "complaint"),
        _output_record("T02", "v2", "fraud_report"),
    ]
    assert changed_queue_count(outputs) == 1


def test_render_notes_uses_counts_and_zero_cost() -> None:
    scores = [
        ScoreRecord(
            run_id="run",
            task="triage",
            case_id="T01",
            model_name="mistral",
            prompt_version=version,
            scorer_version=SCORER_VERSION,
            metric=METRIC_QUEUE,
            numerator=1,
            denominator=1,
        )
        for version in ("v1", "v2")
    ]
    notes = render_notes(
        model_id="mistral:7b",
        run_id="run",
        outputs=[
            _output_record("T01", "v1", "card_dispute"),
            _output_record("T01", "v2", "card_dispute"),
        ],
        scores=scores,
        calls=[
            CallRecord(
                record_id="00000000-0000-4000-8000-000000000001",
                run_id="run",
                timestamp=datetime(2026, 9, 15, tzinfo=UTC),
                provider="ollama",
                model_id="mistral:7b",
                task="triage",
                case_id="T01",
                prompt_id="triage",
                prompt_version="v1",
                attempt=1,
                temperature=0.0,
                max_output_tokens=1024,
                input_tokens=10,
                output_tokens=20,
                cached_input_tokens=None,
                latency_ms=1000,
                cost_usd=0.0,
                stop_reason="stop",
                error_type=None,
                response_text="{}",
            )
        ],
    )
    assert "$0.00" in notes
    assert "queue 1/1" in notes
    assert "%" not in notes
    assert "conclusion:" in notes
