"""Deterministic scoring. This module does not call a model."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from promptlab.config import PII_PATTERNS, PROJECT_ROOT
from promptlab.records import OutputRecord, ScoreRecord
from promptlab.rules import VersionCandidate, select_current_version

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


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def candidate_from_output(
    case_id: str, output: Mapping[str, Any] | None
) -> VersionCandidate | None:
    """Map a validated extraction or summary into a version-rule candidate.

    Both version and effective_date must be present strings, and the date must
    parse as ISO-8601. Anything else is extraction failure, not a candidate.
    """
    if output is None:
        return None
    version = output.get("version")
    effective = output.get("effective_date")
    if not isinstance(version, Mapping) or not isinstance(effective, Mapping):
        return None
    if version.get("status") != "present" or effective.get("status") != "present":
        return None
    version_value = version.get("value")
    effective_date = _iso_date(effective.get("value"))
    if not isinstance(version_value, str) or not version_value.strip():
        return None
    if effective_date is None:
        return None
    return VersionCandidate(
        case_id=case_id,
        version=version_value.strip(),
        effective_date=effective_date,
    )


def _version_groups(
    gold: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for case_id, row in gold.items():
        name = row.get("version_group")
        if not isinstance(name, str) or not name:
            continue
        info = groups.setdefault(
            name,
            {"case_ids": [], "expected": None, "as_of": None, "task": row.get("task")},
        )
        info["case_ids"].append(case_id)
        expected = row.get("expected_current_case_id")
        if isinstance(expected, str) and expected:
            info["expected"] = expected
        as_of = _iso_date(row.get("as_of"))
        if as_of is not None:
            info["as_of"] = as_of
    return groups


def score_version_selection(
    *,
    output_records: Sequence[OutputRecord],
    gold: Mapping[str, Mapping[str, Any]],
) -> list[ScoreRecord]:
    """Score select_current_version against gold version groups.

    One score per model/prompt identity and version group. The model never
    chooses the current document; Python does, using extracted dates.
    """
    groups = {
        name: info
        for name, info in _version_groups(gold).items()
        if len(info["case_ids"]) >= 2
        and info["expected"] is not None
        and info["as_of"] is not None
    }
    if not groups:
        return []

    buckets: dict[tuple[str, str, str, str, str], list[OutputRecord]] = defaultdict(
        list
    )
    for record in output_records:
        buckets[
            (
                record.run_id,
                record.task,
                record.model_id,
                record.prompt_id,
                record.prompt_version,
            )
        ].append(record)

    scores: list[ScoreRecord] = []
    for records in buckets.values():
        by_id = {record.case_id: record for record in records}
        task = records[0].task
        for group_name, info in groups.items():
            if info["task"] not in (None, task):
                continue
            members = [case_id for case_id in info["case_ids"] if case_id in by_id]
            if not members:
                continue
            candidates: list[VersionCandidate] = []
            for case_id in members:
                candidate = candidate_from_output(case_id, by_id[case_id].output)
                if candidate is not None:
                    candidates.append(candidate)
            selected = select_current_version(candidates, info["as_of"])
            expected = info["expected"]
            correct = selected is not None and selected.case_id == expected
            anchor = by_id.get(expected, by_id[members[0]])
            selected_id = selected.case_id if selected is not None else None
            scores.append(
                _record(
                    anchor,
                    "version_selection",
                    int(correct),
                    1,
                    detail=(
                        f"group={group_name} expected={expected} "
                        f"selected={selected_id} "
                        f"candidates={[candidate.case_id for candidate in candidates]}"
                    ),
                )
            )
    return scores


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
