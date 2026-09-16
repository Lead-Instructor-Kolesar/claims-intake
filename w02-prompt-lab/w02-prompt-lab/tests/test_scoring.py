from promptlab.corpus import GoldLabel
from promptlab.schemas import EvidenceField, PolicyExtraction, SummarizationOutput, TriageOutput
from promptlab.scoring import score_output, source_sections


def test_source_sections_reads_numbered_headings() -> None:
    assert source_sections("1. Document Control\nBody\n2. Scope\nText") == {
        "1. document control",
        "2. scope",
    }


def test_evidence_recall_citations_and_unsupported_avoidance() -> None:
    output = PolicyExtraction(
        document_status="valid",
        policy_name=EvidenceField(
            value="Test Policy", status="present", citation="1. Document Control"
        ),
        version=EvidenceField(value="1.0", status="present", citation="1. Document Control"),
        effective_date=EvidenceField(value=None, status="absent"),
        jurisdictions=EvidenceField(value="Pennsylvania", status="present", citation="2. Scope"),
        beneficial_ownership_threshold=EvidenceField(value=None, status="absent"),
        review_frequency=EvidenceField(value="12 months", status="present", citation="4. Review"),
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
        prompt_version="v1",
        output=output,
        gold=gold,
        source=(
            "1. Document Control\nTest Policy 1.0\n2. Scope\nPennsylvania\n"
            "4. Review\n12 months"
        ),
    )
    by_metric = {score.metric: score for score in scores}
    assert by_metric["required_evidence_recall"].numerator == 4
    assert by_metric["required_evidence_recall"].denominator == 4
    assert by_metric["citation_correctness"].numerator == 4
    assert by_metric["citation_correctness"].denominator == 4
    assert by_metric["unsupported_field_avoidance"].numerator == 3
    assert by_metric["unsupported_field_avoidance"].denominator == 3
    assert by_metric["pii_leakage"].numerator == 0


def test_citation_correctness_covers_every_present_extraction_field() -> None:
    output = PolicyExtraction(
        document_status="valid",
        policy_name=EvidenceField(
            value="Test Policy", status="present", citation="1. Document Control"
        ),
        version=EvidenceField(value="1.0", status="present", citation="not a heading"),
        effective_date=EvidenceField(value=None, status="absent"),
        jurisdictions=EvidenceField(value=None, status="absent"),
        beneficial_ownership_threshold=EvidenceField(
            value="51 percent", status="present", citation="6. Reviewer Note"
        ),
        review_frequency=EvidenceField(value=None, status="absent"),
        required_documents=EvidenceField(value=None, status="absent"),
    )
    gold = GoldLabel(
        id="E00",
        task="extraction",
        recoverable_fields=["policy_name", "version"],
    )
    scores = score_output(
        run_id="test",
        task="extraction",
        case_id="E00",
        model_name="test",
        prompt_version="v1",
        output=output,
        gold=gold,
        source="1. Document Control\nTest Policy 1.0\n3. Ownership\n20 percent\n",
    )
    by_metric = {score.metric: score for score in scores}
    assert by_metric["required_evidence_recall"].numerator == 2
    assert by_metric["required_evidence_recall"].denominator == 2
    assert by_metric["citation_correctness"].numerator == 1
    assert by_metric["citation_correctness"].denominator == 3


def test_summarization_does_not_use_extraction_evidence_metrics() -> None:
    output = SummarizationOutput(
        document_status="valid",
        title=EvidenceField(
            value="Lost Card", status="present", citation="1. Document Control"
        ),
        version=EvidenceField(
            value="3.1", status="present", citation="1. Document Control"
        ),
        effective_date=EvidenceField(
            value="2025-03-15", status="present", citation="1. Document Control"
        ),
        purpose=EvidenceField(
            value="Record a lost card.", status="present", citation="2. Purpose"
        ),
        required_steps=EvidenceField(value=None, status="absent"),
        exceptions=EvidenceField(value=None, status="absent"),
    )
    gold = GoldLabel(
        id="S00",
        task="summarization",
        expected_status="valid",
        recoverable_fields=["title", "version", "effective_date", "purpose"],
    )
    scores = score_output(
        run_id="test",
        task="summarization",
        case_id="S00",
        model_name="test",
        prompt_version="v1",
        output=output,
        gold=gold,
        source="1. Document Control\nTitle: Lost Card\n2. Purpose\nRecord a lost card.\n",
    )
    metrics = {score.metric for score in scores}
    assert "required_evidence_recall" not in metrics
    assert "citation_correctness" not in metrics
    by_metric = {score.metric: score for score in scores}
    assert by_metric["document_status"].numerator == 1
    assert by_metric["pii_leakage"].numerator == 0


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
    scores = score_output(
        run_id="test",
        task="triage",
        case_id="T00",
        model_name="test",
        prompt_version="v1",
        output=output,
        gold=gold,
        source="Unauthorized purchase",
    )
    by_metric = {score.metric: score for score in scores}
    assert by_metric["pii_leakage"].numerator == 1
    assert by_metric["pii_leakage"].lower_is_better
    assert by_metric["human_boundary_compliance"].numerator == 0
