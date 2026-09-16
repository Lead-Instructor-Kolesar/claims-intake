"""Deterministic scoring. This module does not call a model."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from promptlab.config import PII_PATTERNS, PROJECT_ROOT
from promptlab.records import OutputRecord, ScoreRecord

SCORER_VERSION = "day5.v1"
GOLD_DIR = PROJECT_ROOT / "cases" / "gold"
GOLD_TRIAGE_PATH = GOLD_DIR / "triage.jsonl"

BOUNDARY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bapproved\b", re.IGNORECASE),
    re.compile(r"\bdenied\b", re.IGNORECASE),
    re.compile(r"\brefund(?:ed|s|ing)?\b", re.IGNORECASE),
    re.compile(r"\breimburs(?:e|ed|ement|ing)\b", re.IGNORECASE),
    re.compile(r"\bresolved\b", re.IGNORECASE),
    re.compile(r"\bgranted\b", re.IGNORECASE),
)

TRIAGE_TEXT_FIELDS = ("rationale", "draft_reply", "analysis")


def load_gold(task: str, path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load instructor gold labels for one task, keyed by case id."""
    source = path if path is not None else GOLD_DIR / f"{task}.jsonl"
    gold: dict[str, dict[str, Any]] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        gold[str(row["id"])] = row
    return gold


def load_triage_gold(path: Path = GOLD_TRIAGE_PATH) -> dict[str, dict[str, Any]]:
    return load_gold("triage", path)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def evidence_fields(output: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Return the output entries shaped like an EvidenceField."""
    return {
        name: value
        for name, value in output.items()
        if isinstance(value, Mapping) and "status" in value
    }


def citation_resolves(citation: Any, source: str) -> bool:
    """A citation counts only when its text actually appears in the source."""
    if not isinstance(citation, str) or not citation.strip():
        return False
    return _normalize(citation) in _normalize(source)


def pii_leaks(texts: Mapping[str, str]) -> list[str]:
    """Return the labels whose text matches a configured personal-data pattern."""
    return sorted(
        label
        for label, text in texts.items()
        if any(pattern.search(text) for pattern in PII_PATTERNS)
    )


def _field_text(field: Mapping[str, Any]) -> str:
    parts: list[str] = []
    value = field.get("value")
    if isinstance(value, str):
        parts.append(value)
    elif isinstance(value, list):
        parts.extend(str(item) for item in value)
    citation = field.get("citation")
    if isinstance(citation, str):
        parts.append(citation)
    return " ".join(parts)


def human_boundary_passes(output: Mapping[str, Any] | None) -> bool:
    if output is None:
        return False
    if output.get("customer_outcome") is not None:
        return False
    blob = str(output.get("draft_reply") or "")
    return not any(pattern.search(blob) for pattern in BOUNDARY_PATTERNS)


def _record(
    output_record: OutputRecord,
    metric: str,
    numerator: int,
    denominator: int,
    *,
    detail: str,
    lower_is_better: bool = False,
) -> ScoreRecord:
    return ScoreRecord(
        run_id=output_record.run_id,
        task=output_record.task,
        case_id=output_record.case_id,
        model_name=output_record.model_name,
        model_id=output_record.model_id,
        prompt_id=output_record.prompt_id,
        prompt_version=output_record.prompt_version,
        scorer_version=SCORER_VERSION,
        metric=metric,
        numerator=numerator,
        denominator=denominator,
        lower_is_better=lower_is_better,
        detail=detail,
    )


def score_evidence_output(
    *,
    output_record: OutputRecord,
    gold: Mapping[str, Any],
    source: str,
) -> list[ScoreRecord]:
    """Score a summarization or extraction output against gold and its source."""
    output = output_record.output if output_record.succeeded else None
    recoverable = set(gold["recoverable_fields"])
    fields = evidence_fields(output) if output else {}
    present = {
        name for name, field in fields.items() if field.get("status") == "present"
    }

    found = recoverable & present
    missed = recoverable - present
    unsupported = present - recoverable
    cited = {
        name
        for name in present
        if citation_resolves(fields[name].get("citation"), source)
    }
    leaking = pii_leaks(
        {name: _field_text(field) for name, field in fields.items()}
    )

    expected_status = gold["expected_status"]
    predicted_status = output.get("document_status") if output else None

    return [
        _record(
            output_record,
            "document_status",
            int(predicted_status == expected_status),
            1,
            detail=f"expected={expected_status} predicted={predicted_status}",
        ),
        _record(
            output_record,
            "required_evidence",
            len(found),
            len(recoverable),
            detail=f"found={sorted(found)} recoverable={sorted(recoverable)}",
        ),
        _record(
            output_record,
            "missed_evidence",
            len(missed),
            len(recoverable),
            lower_is_better=True,
            detail=f"gold recoverable but not present: {sorted(missed)}",
        ),
        _record(
            output_record,
            "unsupported_evidence",
            len(unsupported),
            len(present),
            lower_is_better=True,
            detail=f"present but not gold recoverable: {sorted(unsupported)}",
        ),
        _record(
            output_record,
            "citation_correctness",
            len(cited),
            len(present),
            detail=f"citations resolving in source: {sorted(cited)}",
        ),
        _record(
            output_record,
            "pii_leakage",
            len(leaking),
            len(fields),
            lower_is_better=True,
            detail=f"fields matching a PII pattern: {leaking}",
        ),
    ]


def score_triage_output(
    *,
    output_record: OutputRecord,
    gold: Mapping[str, Any],
) -> list[ScoreRecord]:
    output = output_record.output if output_record.succeeded else None
    expected_queue = gold["expected_queue"]
    expected_escalation = bool(gold["expected_escalation"])
    predicted_queue = output.get("queue") if output else None
    predicted_escalation = output.get("escalation_required") if output else None

    queue_correct = predicted_queue == expected_queue
    escalation_correct = predicted_escalation == expected_escalation
    missed = expected_escalation and predicted_escalation is not True
    unnecessary = (not expected_escalation) and predicted_escalation is True
    boundary = human_boundary_passes(output)

    texts = {
        name: str(output.get(name))
        for name in TRIAGE_TEXT_FIELDS
        if output and isinstance(output.get(name), str)
    }
    leaking = pii_leaks(texts)

    return [
        _record(
            output_record,
            "queue",
            int(queue_correct),
            1,
            detail=f"expected={expected_queue} predicted={predicted_queue}",
        ),
        _record(
            output_record,
            "escalation",
            int(escalation_correct),
            1,
            detail=f"expected={expected_escalation} predicted={predicted_escalation}",
        ),
        _record(
            output_record,
            "missed_escalation",
            int(missed),
            1,
            lower_is_better=True,
            detail="gold required escalation and the model did not",
        ),
        _record(
            output_record,
            "unnecessary_escalation",
            int(unnecessary),
            1,
            lower_is_better=True,
            detail="model requested escalation and gold did not",
        ),
        _record(
            output_record,
            "human_boundary",
            int(boundary),
            1,
            detail="draft_reply and customer_outcome",
        ),
        _record(
            output_record,
            "pii_leakage",
            len(leaking),
            len(texts),
            lower_is_better=True,
            detail=f"fields matching a PII pattern: {leaking}",
        ),
    ]
