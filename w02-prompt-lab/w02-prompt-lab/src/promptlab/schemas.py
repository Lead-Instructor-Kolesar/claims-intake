from __future__ import annotations

import json
import types
from typing import Literal, Union, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

TaskName = Literal["triage", "summarization", "extraction"]
FieldStatus = Literal["present", "absent", "ambiguous"]
DocumentStatus = Literal["valid", "contradictory", "superseded", "unsupported"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceField(StrictModel):
    value: str | list[str] | None
    status: FieldStatus
    citation: str | None = None


class TriageOutput(StrictModel):
    queue: Literal[
        "card_dispute",
        "fraud_report",
        "account_servicing",
        "lending",
        "complaint",
        "escalate",
        "unsupported",
    ]
    escalation_required: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    draft_reply: str
    human_review_required: Literal[True]
    customer_outcome: None = None


class TriageOutputWithAnalysis(TriageOutput):
    analysis: str


class SummarizationOutput(StrictModel):
    document_status: DocumentStatus
    title: EvidenceField
    version: EvidenceField
    effective_date: EvidenceField
    purpose: EvidenceField
    required_steps: EvidenceField
    exceptions: EvidenceField

    def evidence_fields(self) -> dict[str, EvidenceField]:
        return {
            "title": self.title,
            "version": self.version,
            "effective_date": self.effective_date,
            "purpose": self.purpose,
            "required_steps": self.required_steps,
            "exceptions": self.exceptions,
        }


class PolicyExtraction(StrictModel):
    document_status: DocumentStatus
    policy_name: EvidenceField
    version: EvidenceField
    effective_date: EvidenceField
    jurisdictions: EvidenceField
    beneficial_ownership_threshold: EvidenceField
    review_frequency: EvidenceField
    required_documents: EvidenceField

    def evidence_fields(self) -> dict[str, EvidenceField]:
        return {
            "policy_name": self.policy_name,
            "version": self.version,
            "effective_date": self.effective_date,
            "jurisdictions": self.jurisdictions,
            "beneficial_ownership_threshold": self.beneficial_ownership_threshold,
            "review_frequency": self.review_frequency,
            "required_documents": self.required_documents,
        }


OUTPUT_SCHEMAS: dict[TaskName, type[StrictModel]] = {
    "triage": TriageOutput,
    "summarization": SummarizationOutput,
    "extraction": PolicyExtraction,
}


def _is_union(annotation: object) -> bool:
    origin = get_origin(annotation)
    return origin is Union or origin is types.UnionType


def _is_model(annotation: object) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _describe_type(annotation: object) -> object:
    if annotation is type(None):
        return None
    if _is_model(annotation):
        return _instance_guide(cast(type[BaseModel], annotation))
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        if len(args) == 1 and isinstance(args[0], bool):
            return args[0]
        if len(args) == 1 and args[0] is None:
            return None
        return " | ".join(str(arg) for arg in args)
    if _is_union(annotation):
        rendered: list[str] = []
        for arg in args:
            described = _describe_type(arg)
            if isinstance(described, list):
                item = described[0] if described else "any"
                rendered.append(f"list[{item}]")
            elif isinstance(described, dict):
                rendered.append("object")
            else:
                rendered.append(str(described))
        return " | ".join(rendered)
    if origin is list:
        item = _describe_type(args[0]) if args else "any"
        return f"list[{item}]"
    if annotation is str:
        return "string"
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    return str(annotation).replace("typing.", "")


def _instance_guide(model: type[BaseModel]) -> dict[str, object]:
    return {
        name: _describe_type(field.annotation) for name, field in model.model_fields.items()
    }


def schema_description(model: type[BaseModel]) -> str:
    return json.dumps(_instance_guide(model), indent=2)
