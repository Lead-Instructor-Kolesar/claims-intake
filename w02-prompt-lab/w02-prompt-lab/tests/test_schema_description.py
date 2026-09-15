from __future__ import annotations

import json

from promptlab.schemas import PolicyExtraction, SummarizationOutput, schema_description


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
