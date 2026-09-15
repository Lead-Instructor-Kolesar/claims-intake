from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from promptlab.schemas import (
    OUTPUT_SCHEMAS,
    PolicyExtraction,
    SummarizationOutput,
    TriageOutput,
    TriageOutputWithAnalysis,
    schema_description,
)


def test_schema_description_returns_parseable_json_for_summarization() -> None:
    text = schema_description(SummarizationOutput)
    payload = json.loads(text)

    assert isinstance(payload, dict)
    properties = payload.get("properties", {})
    assert "document_status" in properties
    assert "title" in properties
    assert "required_steps" in properties
    assert "exceptions" in properties


def test_schema_description_returns_parseable_json_for_extraction() -> None:
    text = schema_description(PolicyExtraction)
    payload = json.loads(text)

    assert isinstance(payload, dict)
    properties = payload.get("properties", {})
    assert "document_status" in properties
    assert "policy_name" in properties
    assert "beneficial_ownership_threshold" in properties
    assert "required_documents" in properties


def test_triage_output_with_analysis_requires_analysis() -> None:
    payload = {
        "queue": "card_dispute",
        "escalation_required": False,
        "confidence": 0.9,
        "rationale": "Duplicate recognized charge.",
        "draft_reply": "A specialist will review the duplicate charge.",
        "human_review_required": True,
        "customer_outcome": None,
    }
    TriageOutput.model_validate(payload)
    with pytest.raises(ValidationError, match="analysis"):
        TriageOutputWithAnalysis.model_validate(payload)


def test_triage_output_with_analysis_keeps_base_fields() -> None:
    output = TriageOutputWithAnalysis(
        queue="fraud_report",
        escalation_required=False,
        confidence=0.8,
        rationale="Unauthorized activity.",
        draft_reply="A specialist will review the report.",
        human_review_required=True,
        customer_outcome=None,
        analysis="Unrecognized out-of-state charges with card still present.",
    )
    assert output.queue == "fraud_report"
    assert output.escalation_required is False
    assert output.analysis.startswith("Unrecognized")


def test_triage_output_with_analysis_forbids_extra_fields() -> None:
    payload = {
        "queue": "lending",
        "escalation_required": False,
        "confidence": 0.7,
        "rationale": "Loan inquiry.",
        "draft_reply": "A lending specialist will follow up.",
        "human_review_required": True,
        "customer_outcome": None,
        "analysis": "No existing loan problem.",
        "extra": "nope",
    }
    with pytest.raises(ValidationError):
        TriageOutputWithAnalysis.model_validate(payload)


def test_schema_description_includes_analysis_for_v2() -> None:
    payload = json.loads(schema_description(TriageOutputWithAnalysis))
    properties = payload.get("properties", {})
    assert "analysis" in properties
    assert "rationale" in properties
    assert "escalation_required" in properties


def test_output_schemas_triage_stays_base_model() -> None:
    assert OUTPUT_SCHEMAS["triage"] is TriageOutput
