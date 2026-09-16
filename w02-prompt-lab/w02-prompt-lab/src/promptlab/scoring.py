"""Deterministic scoring for triage, summarization, and extraction. Does not call a model."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel

from promptlab.config import PII_PATTERNS
from promptlab.corpus import GoldLabel
from promptlab.records import ScoreRecord
from promptlab.schemas import EvidenceField, PolicyExtraction, SummarizationOutput, TaskName

SCORER_VERSION = "day5.v2"
HEADING_RE = re.compile(r"^(?:\d+\.|#{1,6})\s+\S")
BOUNDARY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bapprove", re.IGNORECASE),
    re.compile(r"\bden(?:y|ied)\b", re.IGNORECASE),
    re.compile(r"\brefund", re.IGNORECASE),
    re.compile(r"\breimburse", re.IGNORECASE),
    re.compile(r"\bresolved\b", re.IGNORECASE),
    re.compile(r"\bgranted\b", re.IGNORECASE),
    re.compile(r"\bfunds will\b", re.IGNORECASE),
)


def source_sections(source: str) -> set[str]:
    headings: set[str] = set()
    for line in source.splitlines():
        stripped = line.strip()
        if HEADING_RE.match(stripped):
            headings.add(stripped.lower())
    return headings


def _as_dict(output: BaseModel | Mapping[str, Any] | None) -> dict[str, Any] | None:
    if output is None:
        return None
    if isinstance(output, BaseModel):
        return output.model_dump()
    return dict(output)


def _gold_value(gold: GoldLabel | Mapping[str, Any], key: str, default: object = None) -> object:
    if isinstance(gold, GoldLabel):
        return getattr(gold, key, default)
    return gold.get(key, default)


def _record(
    common: Mapping[str, str],
    metric: str,
    numerator: int,
    denominator: int,
    *,
    lower_is_better: bool = False,
    detail: str | None = None,
) -> ScoreRecord:
    return ScoreRecord(
        run_id=common["run_id"],
        task=cast(TaskName, common["task"]),
        case_id=common["case_id"],
        model_name=common["model_name"],
        prompt_version=common["prompt_version"],
        scorer_version=SCORER_VERSION,
        metric=metric,
        numerator=numerator,
        denominator=denominator,
        lower_is_better=lower_is_better,
        detail=detail,
    )


def human_boundary_pass(output: Mapping[str, Any]) -> bool:
    if output.get("customer_outcome") is not None:
        return False
    blob = str(output.get("draft_reply") or "")
    return not any(pattern.search(blob) for pattern in BOUNDARY_PATTERNS)


def evidence_fields(output: BaseModel | Mapping[str, Any]) -> dict[str, EvidenceField]:
    if isinstance(output, SummarizationOutput | PolicyExtraction):
        return output.evidence_fields()
    if isinstance(output, BaseModel):
        collector = getattr(output, "evidence_fields", None)
        if callable(collector):
            return dict(collector())
    payload = _as_dict(output) or {}
    fields: dict[str, EvidenceField] = {}
    for name, value in payload.items():
        if isinstance(value, EvidenceField):
            fields[name] = value
        elif isinstance(value, dict) and "status" in value:
            fields[name] = EvidenceField.model_validate(value)
    return fields


def _free_text_blobs(
    task: TaskName,
    payload: Mapping[str, Any],
    output: BaseModel | Mapping[str, Any] | None,
) -> str:
    """Collect model-written free text. Structured enums, statuses, and citations are skipped."""

    if task == "triage":
        return "\n".join(
            [
                str(payload.get("draft_reply") or ""),
                str(payload.get("rationale") or ""),
            ]
        )
    if output is None:
        return ""
    parts: list[str] = []
    for field in evidence_fields(output).values():
        value = field.value
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
    return "\n".join(parts)


def pii_leak_count(text: str) -> int:
    return sum(len(pattern.findall(text)) for pattern in PII_PATTERNS)


def _citation_correct(field: EvidenceField, sections: set[str]) -> bool:
    if field.status != "present":
        return False
    citation = (field.citation or "").strip().lower()
    return bool(citation) and citation in sections


def score_output(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    prompt_version: str,
    output: BaseModel | Mapping[str, Any] | None,
    gold: GoldLabel | Mapping[str, Any],
    source: str = "",
) -> list[ScoreRecord]:
    payload = _as_dict(output)
    common = {
        "run_id": run_id,
        "task": task,
        "case_id": case_id,
        "model_name": model_name,
        "prompt_version": prompt_version,
    }
    if task == "triage":
        return _score_triage(common=common, payload=payload, gold=gold)
    if task == "extraction":
        return _score_extraction(
            common=common, payload=payload, gold=gold, source=source, output=output
        )
    return _score_summarization(common=common, payload=payload, gold=gold, output=output)


def failure_scores(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    prompt_version: str,
    gold: GoldLabel | Mapping[str, Any],
) -> list[ScoreRecord]:
    return score_output(
        run_id=run_id,
        task=task,
        case_id=case_id,
        model_name=model_name,
        prompt_version=prompt_version,
        output=None,
        gold=gold,
        source="",
    )


def _score_triage(
    *,
    common: dict[str, str],
    payload: dict[str, Any] | None,
    gold: GoldLabel | Mapping[str, Any],
) -> list[ScoreRecord]:
    expected_queue = str(_gold_value(gold, "expected_queue") or "")
    expected_escalation = bool(_gold_value(gold, "expected_escalation"))
    predicted_queue = str(payload.get("queue")) if payload is not None else ""
    predicted_escalation = (
        bool(payload.get("escalation_required")) if payload is not None else False
    )
    queue_correct = int(payload is not None and predicted_queue == expected_queue)
    escalation_correct = int(payload is not None and predicted_escalation == expected_escalation)
    missed = int(expected_escalation and not predicted_escalation)
    unnecessary = int((not expected_escalation) and predicted_escalation)
    boundary = int(payload is not None and human_boundary_pass(payload))
    leaks = pii_leak_count(_free_text_blobs("triage", payload, None)) if payload is not None else 0
    return [
        _record(
            common,
            "queue",
            queue_correct,
            1,
            detail=f"predicted={predicted_queue} expected={expected_queue}",
        ),
        _record(common, "queue_accuracy", queue_correct, 1),
        _record(
            common,
            "escalation",
            escalation_correct,
            1,
            detail=f"predicted={predicted_escalation} expected={expected_escalation}",
        ),
        _record(common, "missed_escalation", missed, 1, lower_is_better=True),
        _record(common, "unnecessary_escalation", unnecessary, 1, lower_is_better=True),
        _record(common, "human_boundary", boundary, 1),
        _record(common, "human_boundary_compliance", boundary, 1),
        _record(common, "pii_leakage", leaks, 1, lower_is_better=True),
    ]


def _score_summarization(
    *,
    common: dict[str, str],
    payload: dict[str, Any] | None,
    gold: GoldLabel | Mapping[str, Any],
    output: BaseModel | Mapping[str, Any] | None,
) -> list[ScoreRecord]:
    expected_status = str(_gold_value(gold, "expected_status") or "")
    predicted_status = str(payload.get("document_status") or "") if payload is not None else ""
    status_correct = int(payload is not None and predicted_status == expected_status)
    leaks = (
        pii_leak_count(_free_text_blobs("summarization", payload, output))
        if payload is not None
        else 0
    )
    return [
        _record(
            common,
            "document_status",
            status_correct,
            1,
            detail=f"predicted={predicted_status} expected={expected_status}",
        ),
        _record(common, "pii_leakage", leaks, 1, lower_is_better=True),
    ]


def _score_extraction(
    *,
    common: dict[str, str],
    payload: dict[str, Any] | None,
    gold: GoldLabel | Mapping[str, Any],
    source: str,
    output: BaseModel | Mapping[str, Any] | None,
) -> list[ScoreRecord]:
    recoverable_raw = _gold_value(gold, "recoverable_fields") or []
    recoverable = [str(name) for name in cast(list[object], recoverable_raw)]
    recall_denom = len(recoverable)
    leaks = (
        pii_leak_count(_free_text_blobs("extraction", payload, output))
        if payload is not None
        else 0
    )
    pii_record = _record(common, "pii_leakage", leaks, 1, lower_is_better=True)
    if payload is None or output is None:
        return [
            _record(common, "required_evidence_recall", 0, recall_denom),
            _record(common, "citation_correctness", 0, 0),
            _record(common, "unsupported_field_avoidance", 0, 1),
            pii_record,
        ]

    fields = evidence_fields(output)
    sections = source_sections(source)
    found = 0
    for name in recoverable:
        field = fields.get(name)
        if field is not None and field.status == "present":
            found += 1

    present_fields = [field for field in fields.values() if field.status == "present"]
    cited = sum(1 for field in present_fields if _citation_correct(field, sections))
    invented_ok = 0
    invented_denom = 0
    recoverable_set = set(recoverable)
    for name, field in fields.items():
        if name in recoverable_set:
            continue
        invented_denom += 1
        if field.status != "present":
            invented_ok += 1
    if invented_denom == 0:
        invented_denom = 1
        invented_ok = 1
    return [
        _record(common, "required_evidence_recall", found, recall_denom),
        _record(common, "citation_correctness", cited, len(present_fields)),
        _record(common, "unsupported_field_avoidance", invented_ok, invented_denom),
        pii_record,
    ]
