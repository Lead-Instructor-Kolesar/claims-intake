from __future__ import annotations

import json
from typing import Any, Literal

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


class ProcedureSummary(StrictModel):
    document_status: DocumentStatus
    version: EvidenceField
    effective_date: EvidenceField
    superseded: EvidenceField
    scope: EvidenceField
    required_analyst_actions: EvidenceField
    evidence_to_gather: EvidenceField
    deadlines: EvidenceField
    out_of_scope: EvidenceField

    def evidence_fields(self) -> dict[str, EvidenceField]:
        return {
            "version": self.version,
            "effective_date": self.effective_date,
            "superseded": self.superseded,
            "scope": self.scope,
            "required_analyst_actions": self.required_analyst_actions,
            "evidence_to_gather": self.evidence_to_gather,
            "deadlines": self.deadlines,
            "out_of_scope": self.out_of_scope,
        }


def schema_description(model: type[BaseModel]) -> str:
    """Return a generated description of a valid JSON instance for this model."""
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    title = str(schema.get("title", model.__name__))
    required = set(schema.get("required", []))
    lines = [
        f"Emit one JSON object that is an instance of {title}.",
        "Do not emit a JSON Schema document.",
        "Do not include keys named $defs, properties, additionalProperties, or required.",
        "Object fields:",
    ]
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for name, spec in properties.items():
            if not isinstance(spec, dict):
                continue
            requirement = "required" if name in required else "optional"
            lines.append(f"- {name} ({requirement}): {_field_line(spec, defs)}")
    lines.append("Every listed field is required, including nested value keys.")
    lines.append("Use null for value and citation when status is absent.")
    lines.append("Do not add fields that are not listed.")
    lines.append("Example instance shape (replace placeholders from the document):")
    lines.append(json.dumps(_placeholder_instance(schema, defs), indent=2))
    return "\n".join(lines)


def _field_line(spec: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in spec:
        ref_name = str(spec["$ref"]).rsplit("/", 1)[-1]
        target = defs.get(ref_name, {})
        if isinstance(target, dict):
            return f"{ref_name} object with {_inline_fields(target, defs)}"
        return ref_name
    if "enum" in spec:
        options = spec["enum"]
        if isinstance(options, list):
            return "one of " + ", ".join(json.dumps(item) for item in options)
    variants = spec.get("anyOf") or spec.get("oneOf")
    if isinstance(variants, list):
        parts = [_field_line(part, defs) for part in variants if isinstance(part, dict)]
        return " or ".join(parts)
    type_name = spec.get("type")
    if isinstance(type_name, str):
        return type_name
    return "value"


def _inline_fields(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return "{}"
    parts: list[str] = []
    required = set(schema.get("required", []))
    for name, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        requirement = "required" if name in required else "optional"
        parts.append(f"{name} ({requirement}: {_field_line(spec, defs)})")
    return "{" + ", ".join(parts) + "}"


def _placeholder_instance(schema: dict[str, Any], defs: dict[str, Any]) -> Any:
    if "$ref" in schema:
        ref_name = str(schema["$ref"]).rsplit("/", 1)[-1]
        target = defs.get(ref_name, {})
        if isinstance(target, dict):
            return _placeholder_instance(target, defs)
        return None
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]
    variants = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(variants, list):
        for variant in variants:
            if isinstance(variant, dict) and variant.get("type") == "null":
                return None
        for variant in variants:
            if isinstance(variant, dict):
                return _placeholder_instance(variant, defs)
        return None
    type_name = schema.get("type")
    if type_name == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return {}
        return {
            name: _placeholder_instance(spec, defs)
            for name, spec in properties.items()
            if isinstance(spec, dict)
        }
    if type_name == "array":
        return []
    if type_name == "boolean":
        return False
    if type_name in {"integer", "number"}:
        return 0
    if type_name == "null":
        return None
    return None


OUTPUT_SCHEMAS: dict[TaskName, type[StrictModel]] = {
    "triage": TriageOutput,
    "summarization": SummarizationOutput,
    "extraction": PolicyExtraction,
}

