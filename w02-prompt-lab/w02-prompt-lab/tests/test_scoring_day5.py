"""Day 5 deterministic scorer tests: evidence recall, citations, PII, version rule.

No model calls. Each test feeds hand-built outputs and gold fields so the
counts with denominators are exact.
"""

from __future__ import annotations

from typing import Any

from promptlab.records import ScoreRecord
from promptlab.scoring import (
    METRIC_CITATION_CORRECTNESS,
    METRIC_PII_LEAKAGE,
    METRIC_REQUIRED_EVIDENCE_RECALL,
    METRIC_VERSION_SELECTION,
    SCORER_VERSION,
    score_evidence_case,
    score_pii_case,
    score_version_selection,
)

SOURCE = """1. Document Control
Policy name: Small Business Periodic KYC
2. Review
Reviewed every year.
"""


def field(
    value: str | list[str] | None, status: str, citation: str | None = None
) -> dict[str, Any]:
    return {"value": value, "status": status, "citation": citation}


def evidence_records(
    output: dict[str, Any], recoverable: list[str]
) -> list[ScoreRecord]:
    return score_evidence_case(
        run_id="r",
        task="extraction",
        case_id="E01",
        model_name="mistral",
        prompt_version="v2",
        prompt_id="extract",
        source_text=SOURCE,
        recoverable_fields=recoverable,
        output=output,
    )


def test_recall_counts_present_recoverable_fields() -> None:
    output = {
        "policy_name": field("Small Business KYC", "present", "1. Document Control"),
        "version": field("1.0", "absent"),
    }
    records = evidence_records(output, ["policy_name", "version"])
    recall = next(r for r in records if r.metric == METRIC_REQUIRED_EVIDENCE_RECALL)
    assert (recall.numerator, recall.denominator) == (1, 2)
    assert recall.prompt_id == "extract"
    assert recall.scorer_version == SCORER_VERSION
    assert "version" in (recall.detail or "")


def test_recall_treats_blank_present_value_as_missing() -> None:
    output = {"policy_name": field("   ", "present", None)}
    records = evidence_records(output, ["policy_name"])
    recall = next(r for r in records if r.metric == METRIC_REQUIRED_EVIDENCE_RECALL)
    assert (recall.numerator, recall.denominator) == (0, 1)


def test_citation_correctness_requires_a_real_heading() -> None:
    output = {
        "policy_name": field("Small Business KYC", "present", "1. Document Control"),
        "review_frequency": field("every year", "present", "3"),
    }
    records = evidence_records(output, ["policy_name"])
    citation = next(r for r in records if r.metric == METRIC_CITATION_CORRECTNESS)
    assert (citation.numerator, citation.denominator) == (1, 2)
    assert "review_frequency" in (citation.detail or "")


def test_citation_skipped_when_nothing_is_present() -> None:
    records = evidence_records({}, ["policy_name"])
    assert all(r.metric != METRIC_CITATION_CORRECTNESS for r in records)


def test_absent_heading_form_accepts_bare_heading_text() -> None:
    output = {
        "policy_name": field("Small Business KYC", "present", "Section 1. Document Control"),
    }
    records = evidence_records(output, ["policy_name"])
    citation = next(r for r in records if r.metric == METRIC_CITATION_CORRECTNESS)
    assert (citation.numerator, citation.denominator) == (1, 1)


def test_pii_leakage_flags_ssn_and_email() -> None:
    record = score_pii_case(
        run_id="r",
        task="triage",
        case_id="T01",
        model_name="mistral",
        prompt_version="v2",
        prompt_id="triage",
        texts=["Your SSN 123-45-6789 is on file", "mail us at a@b.com"],
    )
    assert record.metric == METRIC_PII_LEAKAGE
    assert (record.numerator, record.denominator) == (1, 1)
    assert record.lower_is_better is True
    assert record.detail is not None and "123-45-6789" in record.detail


def test_pii_leakage_passes_clean_text() -> None:
    record = score_pii_case(
        run_id="r",
        task="triage",
        case_id="T01",
        model_name="mistral",
        prompt_version="v2",
        texts=["We will review the charge and contact you."],
    )
    assert (record.numerator, record.denominator) == (0, 1)
    assert record.detail is None


def test_version_selection_scores_only_exact_matches() -> None:
    hit = score_version_selection(
        run_id="r",
        task="extraction",
        case_id="VG:group",
        model_name="mistral",
        prompt_version="v2",
        selected_case_id="E02",
        expected_case_id="E02",
    )
    miss = score_version_selection(
        run_id="r",
        task="extraction",
        case_id="VG:group",
        model_name="mistral",
        prompt_version="v2",
        selected_case_id=None,
        expected_case_id="E02",
        rule_detail="rule returned None (ambiguous effective dates)",
    )
    assert hit.metric == METRIC_VERSION_SELECTION
    assert (hit.numerator, hit.denominator) == (1, 1)
    assert (miss.numerator, miss.denominator) == (0, 1)
    assert "rule returned None" in (miss.detail or "")
