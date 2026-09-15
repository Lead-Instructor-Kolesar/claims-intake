"""Offline tests for schema_description."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from promptlab.schemas import PolicyExtraction, SummarizationOutput, schema_description


def test_policy_extraction_description_lists_every_field_name() -> None:
    description = schema_description(PolicyExtraction)

    for name in (
        "policy_name",
        "jurisdictions",
        "beneficial_ownership_threshold",
        "review_frequency",
        "required_documents",
        "document_status",
        "version",
        "effective_date",
    ):
        assert name in description
    assert "EvidenceField" in description


def test_policy_extraction_description_includes_literal_vocabularies() -> None:
    description = schema_description(PolicyExtraction)

    for vocabulary in ("present", "absent", "ambiguous"):
        assert f'"{vocabulary}"' in description
    for vocabulary in ("valid", "contradictory", "superseded", "unsupported"):
        assert f'"{vocabulary}"' in description


def test_policy_extraction_description_includes_citation() -> None:
    assert "citation" in schema_description(PolicyExtraction)


def test_description_is_deterministic() -> None:
    assert schema_description(PolicyExtraction) == schema_description(PolicyExtraction)


def test_plain_model_description_lists_fields_and_basic_types() -> None:
    class Recipe(BaseModel):
        name: str
        servings: int

    description = schema_description(Recipe)

    assert "name" in description
    assert "servings" in description
    assert "string" in description
    assert "integer" in description


def test_nested_model_fields_are_described() -> None:
    description = schema_description(PolicyExtraction)

    for name in ("value", "status", "citation"):
        assert name in description


def test_description_is_not_itself_a_json_object() -> None:
    description = schema_description(SummarizationOutput)

    with pytest.raises(ValueError):
        json.loads(description)
    assert "$defs" not in description
    assert "additionalProperties" not in description


def test_description_forbids_returning_the_description_itself() -> None:
    description = schema_description(SummarizationOutput)

    assert "Do not return this description" in description
    assert "concrete values" in description
