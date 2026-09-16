"""Offline tests for schema_description."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from promptlab.schemas import (
    PolicyExtraction,
    SummarizationOutput,
    TriageOutput,
    TriageOutputWithAnalysis,
    schema_description,
)


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


def test_description_does_not_model_a_wrapper_key() -> None:
    description = schema_description(SummarizationOutput)

    assert not description.startswith(f"{SummarizationOutput.__name__}:")
    assert "Do not wrap the object under another key" in description


def _top_level_field_names(description: str) -> list[str]:
    names: list[str] = []
    for line in description.splitlines():
        if not line.startswith("  "):
            continue
        names.append(line.strip().split(":", 1)[0])
    return names


def test_analysis_field_is_listed_first_for_v2() -> None:
    v2_names = _top_level_field_names(schema_description(TriageOutputWithAnalysis))
    v1_names = _top_level_field_names(schema_description(TriageOutput))

    assert v2_names[0] == "analysis"
    assert "analysis" not in v1_names
    assert v2_names[1:] == v1_names
