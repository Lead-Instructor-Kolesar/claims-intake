from __future__ import annotations

import json
from types import UnionType
from typing import Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field
from pydantic.fields import FieldInfo

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


def schema_description(model: type[BaseModel]) -> str:
    """Return a compact description of the supplied model for embedding in prompts.

    The description is generated from the model definition so prompts never
    carry a hand-maintained copy of the output shape. It is deliberately not
    JSON, so the model cannot echo it back as if it were the answer object.
    """
    nested: list[type[BaseModel]] = []
    lines = ["Return ONE JSON object with exactly these top-level fields:"]
    for name, field_info in model.model_fields.items():
        lines.append(_field_line(name, field_info, nested))

    index = 0
    while index < len(nested):
        nested_model = nested[index]
        index += 1
        lines.append("")
        lines.append(
            f"{nested_model.__name__} is itself a JSON object with exactly these fields:"
        )
        for name, field_info in nested_model.model_fields.items():
            lines.append(_field_line(name, field_info, nested))

    lines.append("")
    lines.append(
        "Return exactly one JSON object whose top-level keys are exactly the field "
        "names above, holding concrete values. Do not wrap the object under another "
        "key such as a schema name. Do not return this description, do not return "
        "schema text, and do not use Markdown."
    )
    return "\n".join(lines)


def _field_line(name: str, field_info: FieldInfo, nested: list[type[BaseModel]]) -> str:
    annotation = _describe_annotation(field_info.annotation, nested)
    required = "" if field_info.is_required() else " (optional)"
    return f"  {name}: {annotation}{required}"


_PRIMITIVE_NAMES: dict[object, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _describe_annotation(
    annotation: object,
    nested: list[type[BaseModel]],
) -> str:
    if annotation is None or annotation is type(None):
        return "null"
    primitive = _PRIMITIVE_NAMES.get(annotation)
    if primitive is not None:
        return primitive
    origin = get_origin(annotation)
    if origin is None:
        if isinstance(annotation, type):
            if issubclass(annotation, BaseModel):
                if annotation not in nested:
                    nested.append(annotation)
                return annotation.__name__
            return annotation.__name__
        return str(annotation)
    args = get_args(annotation)
    if origin is Literal:
        return "one of " + ", ".join(json.dumps(arg) for arg in args)
    if origin is list:
        return f"list of {_describe_annotation(args[0], nested)}"
    if origin is Union or origin is UnionType:
        return " or ".join(_describe_annotation(arg, nested) for arg in args)
    return str(annotation)