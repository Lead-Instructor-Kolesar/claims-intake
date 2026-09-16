from typing import Any

from promptlab.records import OutputRecord
from promptlab.scoring import (
    SCORER_VERSION,
    citation_resolves,
    pii_leaks,
    score_evidence_output,
    score_triage_output,
)

SOURCE = (
    "Title: Card Dispute Intake\n"
    "Version: 2.0\n"
    "Effective Date: 2025-06-01\n"
    "Purpose: Route disputed card transactions to the intake queue.\n"
)


def evidence_record(output: dict[str, Any] | None) -> OutputRecord:
    return OutputRecord(
        run_id="run-1",
        task="summarization",
        case_id="S01",
        model_name="mistral",
        model_id="mistral:7b",
        prompt_id="summarize",
        prompt_version="v1",
        succeeded=output is not None,
        repairs=0,
        output=output,
    )


def triage_record(output: dict[str, Any] | None) -> OutputRecord:
    return OutputRecord(
        run_id="run-1",
        task="triage",
        case_id="T11",
        model_name="mistral",
        model_id="mistral:7b",
        prompt_id="triage",
        prompt_version="v1",
        succeeded=output is not None,
        repairs=0,
        output=output,
    )


def metrics(records: list[Any]) -> dict[str, tuple[int, int]]:
    return {r.metric: (r.numerator, r.denominator) for r in records}


def test_recall_counts_only_gold_recoverable_fields() -> None:
    output = {
        "document_status": "valid",
        "title": {"value": "Card Dispute Intake", "status": "present", "citation": None},
        "version": {"value": "2.0", "status": "present", "citation": None},
        "effective_date": {"value": None, "status": "absent", "citation": None},
    }
    scores = metrics(
        score_evidence_output(
            output_record=evidence_record(output),
            gold={
                "expected_status": "valid",
                "recoverable_fields": ["title", "version", "effective_date"],
            },
            source=SOURCE,
        )
    )
    assert scores["required_evidence"] == (2, 3)
    assert scores["missed_evidence"] == (1, 3)
    assert scores["unsupported_evidence"] == (0, 2)
    assert scores["document_status"] == (1, 1)


def test_present_field_outside_gold_is_unsupported() -> None:
    output = {
        "document_status": "unsupported",
        "title": {"value": "Invented Policy", "status": "present", "citation": None},
    }
    scores = metrics(
        score_evidence_output(
            output_record=evidence_record(output),
            gold={"expected_status": "unsupported", "recoverable_fields": []},
            source=SOURCE,
        )
    )
    assert scores["required_evidence"] == (0, 0)
    assert scores["unsupported_evidence"] == (1, 1)


def test_citation_must_appear_in_source() -> None:
    output = {
        "document_status": "valid",
        "title": {
            "value": "Card Dispute Intake",
            "status": "present",
            "citation": "Title: Card Dispute Intake",
        },
        "version": {
            "value": "2.0",
            "status": "present",
            "citation": "Appendix Q: Nonexistent Section",
        },
    }
    scores = metrics(
        score_evidence_output(
            output_record=evidence_record(output),
            gold={
                "expected_status": "valid",
                "recoverable_fields": ["title", "version"],
            },
            source=SOURCE,
        )
    )
    assert scores["citation_correctness"] == (1, 2)


def test_missing_citation_does_not_count_as_correct() -> None:
    assert citation_resolves(None, SOURCE) is False
    assert citation_resolves("   ", SOURCE) is False
    assert citation_resolves("Version: 2.0", SOURCE) is True


def test_pii_leak_detected_in_triage_free_text() -> None:
    output = {
        "queue": "card_dispute",
        "escalation_required": False,
        "confidence": 0.8,
        "rationale": "Duplicate restaurant charge reported.",
        "draft_reply": "We will review account 8812046631 shortly.",
        "human_review_required": True,
        "customer_outcome": None,
    }
    scores = metrics(
        score_triage_output(
            output_record=triage_record(output),
            gold={"expected_queue": "card_dispute", "expected_escalation": False},
        )
    )
    assert scores["pii_leakage"] == (1, 2)
    assert scores["queue"] == (1, 1)


def test_clean_triage_output_reports_no_leak() -> None:
    output = {
        "queue": "card_dispute",
        "escalation_required": False,
        "confidence": 0.8,
        "rationale": "Duplicate restaurant charge reported.",
        "draft_reply": "A specialist will review the duplicate charge.",
        "human_review_required": True,
        "customer_outcome": None,
    }
    scores = metrics(
        score_triage_output(
            output_record=triage_record(output),
            gold={"expected_queue": "card_dispute", "expected_escalation": False},
        )
    )
    assert scores["pii_leakage"] == (0, 2)
    assert scores["human_boundary"] == (1, 1)


def test_pii_patterns_match_corpus_formats() -> None:
    leaks = pii_leaks(
        {
            "ssn": "SSN is 321-54-9876",
            "email": "marina.ellis@example.test",
            "phone": "215-555-0148",
            "account": "8812046631",
            "clean": "No identifiers here.",
        }
    )
    assert leaks == ["account", "email", "phone", "ssn"]


def test_failed_case_still_produces_scores() -> None:
    scores = metrics(
        score_evidence_output(
            output_record=evidence_record(None),
            gold={
                "expected_status": "valid",
                "recoverable_fields": ["title", "version"],
            },
            source=SOURCE,
        )
    )
    assert scores["required_evidence"] == (0, 2)
    assert scores["missed_evidence"] == (2, 2)
    assert scores["document_status"] == (0, 1)


def test_scorer_version_is_incremented_past_day4() -> None:
    assert SCORER_VERSION == "day5.v1"
