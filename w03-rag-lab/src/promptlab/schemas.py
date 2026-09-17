"""Extraction schemas. Week 2 reference implementation.

Evidence is generic because the status, citation, and note logic is identical for
every field. Writing it once means the rule that present requires a citation is
enforced everywhere rather than remembered in eight places.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

T = TypeVar("T")


class FieldStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    AMBIGUOUS = "ambiguous"


class Evidence(BaseModel, Generic[T]):
    """One extracted field, carrying its own status and citation."""

    model_config = ConfigDict(extra="forbid")

    status: FieldStatus
    value: T | None = None
    section: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def status_matches_content(self) -> Evidence[T]:
        if self.status is FieldStatus.PRESENT:
            if self.value is None or self.section is None:
                raise ValueError("present requires both value and section")
        if self.status is FieldStatus.ABSENT and self.value is not None:
            raise ValueError("absent must not carry a value")
        if self.status is FieldStatus.AMBIGUOUS and not self.note:
            raise ValueError("ambiguous requires a note describing the conflict")
        return self


class PolicyExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_kind: Literal["kyc_periodic_review_policy", "other"]
    out_of_scope_reason: str | None = None

    document_version: Evidence[str]
    effective_date: Evidence[str]
    superseded_by: Evidence[str]
    entity_types_in_scope: Evidence[list[str]]
    review_triggers: Evidence[list[str]]
    required_documents: Evidence[list[str]]
    beneficial_ownership_threshold_percent: Evidence[float]
    jurisdictions: Evidence[list[str]]

    @model_validator(mode="after")
    def out_of_scope_is_explained(self) -> PolicyExtraction:
        if self.document_kind == "other" and not self.out_of_scope_reason:
            raise ValueError("document_kind 'other' requires out_of_scope_reason")
        return self


def schema_description(model: type[BaseModel]) -> str:
    """Produce the text a prompt uses to describe its required output.

    Prompts call this rather than restating the structure, so the schema stays the
    only definition of the contract.
    """
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True)
