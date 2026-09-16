from __future__ import annotations

from datetime import date

from promptlab.corpus import GoldLabel
from promptlab.rules import VersionCandidate
from promptlab.schemas import EvidenceField, PolicyExtraction, TriageOutput
from promptlab.scoring import (
    SCORER_VERSION,
    failure_scores,
    score_output,
    score_version_selection,
    source_sections,
)


def test_source_sections_reads_numbered_and_markdown_headings() -> None:
    assert source_sections("1. Document Control\nBody\n2. Scope\nText") == {
        "1. document control",
        "2. scope",
    }
    assert source_sections("# Title\n## Review Cadence\nBody") == {
        "title",
        "# title",
        "review cadence",
        "## review cadence",
    }


def test_evidence_recall_citations_and_unsupported_avoidance() -> None:
    output = PolicyExtraction(
        document_status="valid",
        policy_name=EvidenceField(
            value="Test Policy", status="present", citation="1. Document Control"
        ),
        version=EvidenceField(value="1.0", status="present", citation="1. Document Control"),
        effective_date=EvidenceField(value=None, status="absent"),
        jurisdictions=EvidenceField(
            value="Pennsylvania", status="present", citation="2. Scope"
        ),
        beneficial_ownership_threshold=EvidenceField(value=None, status="absent"),
        review_frequency=EvidenceField(
            value="12 months", status="present", citation="4. Review"
        ),
        required_documents=EvidenceField(value=None, status="absent"),
    )
    gold = GoldLabel(
        id="E00",
        task="extraction",
        expected_status="valid",
        recoverable_fields=["policy_name", "version", "jurisdictions", "review_frequency"],
    )
    scores = score_output(
        run_id="test",
        task="extraction",
        case_id="E00",
        model_name="test",
        prompt_version="v2",
        output=output,
        gold=gold,
        source=(
            "1. Document Control\nTest Policy 1.0\n2. Scope\nPennsylvania\n"
            "4. Review\n12 months"
        ),
    )
    by_metric = {score.metric: score for score in scores}
    assert by_metric["document_status_accuracy"].numerator == 1
    assert by_metric["required_evidence_recall"].numerator == 4
    assert by_metric["required_evidence_recall"].denominator == 4
    assert by_metric["missing_required_evidence"].numerator == 0
    assert by_metric["missing_required_evidence"].lower_is_better is True
    assert by_metric["citation_correctness"].numerator == 4
    assert by_metric["citation_correctness"].denominator == 4
    assert by_metric["unsupported_field_avoidance"].numerator == 3
    assert by_metric["unsupported_field_avoidance"].denominator == 3
    assert by_metric["unsupported_field_invention"].numerator == 0
    assert by_metric["unsupported_field_invention"].lower_is_better is True
    assert by_metric["pii_leakage"].numerator == 0
    assert {score.scorer_version for score in scores} == {SCORER_VERSION}


def test_missed_and_invented_are_tracked_separately() -> None:
    output = PolicyExtraction(
        document_status="valid",
        policy_name=EvidenceField(
            value="Test Policy", status="present", citation="1. Document Control"
        ),
        version=EvidenceField(value=None, status="absent"),
        effective_date=EvidenceField(
            value="2024-01-01", status="present", citation="1. Document Control"
        ),
        jurisdictions=EvidenceField(value=None, status="absent"),
        beneficial_ownership_threshold=EvidenceField(value=None, status="absent"),
        review_frequency=EvidenceField(value=None, status="absent"),
        required_documents=EvidenceField(value=None, status="absent"),
    )
    gold = GoldLabel(
        id="E00",
        task="extraction",
        expected_status="valid",
        recoverable_fields=["policy_name", "version", "jurisdictions", "review_frequency"],
    )
    by_metric = {
        score.metric: score
        for score in score_output(
            run_id="test",
            task="extraction",
            case_id="E00",
            model_name="test",
            prompt_version="v2",
            output=output,
            gold=gold,
            source="1. Document Control\nTest Policy",
        )
    }
    assert by_metric["required_evidence_recall"].numerator == 1
    assert by_metric["missing_required_evidence"].numerator == 3
    assert by_metric["unsupported_field_invention"].numerator == 1
    assert by_metric["unsupported_field_avoidance"].numerator == 2


def test_citation_correctness_rejects_unknown_headings() -> None:
    output = PolicyExtraction(
        document_status="valid",
        policy_name=EvidenceField(
            value="Test Policy", status="present", citation="Made Up Heading"
        ),
        version=EvidenceField(value=None, status="absent"),
        effective_date=EvidenceField(value=None, status="absent"),
        jurisdictions=EvidenceField(value=None, status="absent"),
        beneficial_ownership_threshold=EvidenceField(value=None, status="absent"),
        review_frequency=EvidenceField(value=None, status="absent"),
        required_documents=EvidenceField(value=None, status="absent"),
    )
    gold = GoldLabel(
        id="E00",
        task="extraction",
        expected_status="valid",
        recoverable_fields=["policy_name"],
    )
    by_metric = {
        score.metric: score
        for score in score_output(
            run_id="test",
            task="extraction",
            case_id="E00",
            model_name="test",
            prompt_version="v2",
            output=output,
            gold=gold,
            source="1. Document Control\nTest Policy",
        )
    }
    assert by_metric["citation_correctness"].numerator == 0
    assert by_metric["citation_correctness"].denominator == 1


def test_pii_families_detected_in_free_text() -> None:
    samples = (
        "SSN 123-45-6789",
        "account 1234567890",
        "email a.b@example.com",
        "call 215-555-0148",
    )
    gold = GoldLabel(
        id="T00",
        task="triage",
        expected_queue="fraud_report",
        expected_escalation=False,
    )
    for sample in samples:
        output = TriageOutput(
            queue="fraud_report",
            escalation_required=False,
            confidence=0.9,
            rationale="Unauthorized activity",
            draft_reply=sample,
            human_review_required=True,
            customer_outcome=None,
        )
        by_metric = {
            score.metric: score
            for score in score_output(
                run_id="test",
                task="triage",
                case_id="T00",
                model_name="test",
                prompt_version="v1",
                output=output,
                gold=gold,
                source="Unauthorized purchase 123-45-6789",
            )
        }
        assert by_metric["pii_leakage"].numerator == 1
        assert by_metric["pii_leakage"].lower_is_better is True


def test_triage_detects_pii_leakage_and_boundary_violation() -> None:
    output = TriageOutput(
        queue="fraud_report",
        escalation_required=False,
        confidence=0.9,
        rationale="Unauthorized activity",
        draft_reply="We approved your claim. Call 215-555-0148.",
        human_review_required=True,
        customer_outcome=None,
    )
    gold = GoldLabel(
        id="T00",
        task="triage",
        expected_queue="fraud_report",
        expected_escalation=False,
    )
    by_metric = {
        score.metric: score
        for score in score_output(
            run_id="test",
            task="triage",
            case_id="T00",
            model_name="test",
            prompt_version="v1",
            output=output,
            gold=gold,
            source="Unauthorized purchase",
        )
    }
    assert by_metric["pii_leakage"].numerator == 1
    assert by_metric["human_boundary_compliance"].numerator == 0
    assert "queue_accuracy" in by_metric


def test_failure_scores_keep_denominators() -> None:
    gold = GoldLabel(
        id="E00",
        task="extraction",
        expected_status="valid",
        recoverable_fields=["policy_name", "version", "jurisdictions", "review_frequency"],
    )
    scores = failure_scores(
        run_id="test",
        task="extraction",
        case_id="E00",
        model_name="test",
        prompt_version="v2",
        gold=gold,
    )
    by_metric = {score.metric: score for score in scores}
    assert by_metric["required_evidence_recall"].numerator == 0
    assert by_metric["required_evidence_recall"].denominator == 4
    # A truncated/failed case missed every recoverable field.
    assert by_metric["missing_required_evidence"].numerator == 4
    assert by_metric["missing_required_evidence"].denominator == 4
    assert by_metric["missing_required_evidence"].lower_is_better is True
    assert by_metric["citation_correctness"].numerator == 0
    assert by_metric["citation_correctness"].denominator == 4
    assert by_metric["unsupported_field_avoidance"].denominator == 3
    assert by_metric["document_status_accuracy"].denominator == 1
    assert all(score.detail == "No validated output" for score in scores)


def test_version_selection_accuracy() -> None:
    record = score_version_selection(
        run_id="test",
        task="extraction",
        model_name="mistral",
        prompt_version="v2",
        group_name="small-business-periodic-kyc",
        expected_case_id="E02",
        as_of=date(2025, 6, 1),
        candidates=[
            VersionCandidate(
                case_id="E01", version="1.0", effective_date=date(2024, 1, 1)
            ),
            VersionCandidate(
                case_id="E02", version="2.0", effective_date=date(2025, 1, 1)
            ),
        ],
    )
    assert record.metric == "version_selection_accuracy"
    assert record.case_id == "E02"
    assert record.numerator == 1
    assert "small-business-periodic-kyc" in (record.detail or "")
