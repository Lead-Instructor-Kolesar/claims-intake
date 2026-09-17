"""Deterministic Day 4 triage scoring. No model calls.

Scores the existing TriageOutput fields against gold labels using the
repository ScoreRecord contract. Escalation is always compared through
``escalation_required`` and gold ``expected_escalation``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from promptlab.config import PII_PATTERNS
from promptlab.records import ScoreRecord
from promptlab.schemas import TaskName

SCORER_VERSION = "day5.v1"

METRIC_QUEUE = "queue"
METRIC_ESCALATION = "escalation"
METRIC_MISSED_ESCALATION = "missed_escalation"
METRIC_UNNECESSARY_ESCALATION = "unnecessary_escalation"
METRIC_HUMAN_BOUNDARY = "human_boundary"
METRIC_REQUIRED_EVIDENCE_RECALL = "required_evidence_recall"
METRIC_CITATION_CORRECTNESS = "citation_correctness"
METRIC_PII_LEAKAGE = "pii_leakage"
METRIC_VERSION_SELECTION = "version_selection"

# config.py ships PII_PATTERNS only, not boundary language. These patterns are
# the deterministic human-boundary check for draft_reply and customer_outcome.
_BOUNDARY_LANGUAGE = re.compile(
    r"\b("
    r"approved|approval|"
    r"refund(?:ed|s)?|"
    r"reimburs(?:e|ed|ement)|"
    r"denied|denial|"
    r"resolved|resolution|"
    r"granted"
    r")\b",
    re.IGNORECASE,
)


def _unit(passed: bool) -> tuple[int, int]:
    return (1 if passed else 0, 1)


def _predicted_escalation(output: Mapping[str, Any] | None) -> bool | None:
    """Return the model's escalation_required value, or None if it is absent."""
    if output is None:
        return None
    value = output.get("escalation_required")
    if isinstance(value, bool):
        return value
    return None


def _boundary_corpus(output: Mapping[str, Any] | None) -> str:
    if output is None:
        return ""
    parts: list[str] = []
    draft_reply = output.get("draft_reply")
    if isinstance(draft_reply, str):
        parts.append(draft_reply)
    customer_outcome = output.get("customer_outcome")
    if customer_outcome is not None:
        parts.append(str(customer_outcome))
    return "\n".join(parts)


def _boundary_hits(text: str) -> list[str]:
    return [match.group(0) for match in _BOUNDARY_LANGUAGE.finditer(text)]


def score_case(
    *,
    run_id: str,
    case_id: str,
    model_name: str,
    prompt_version: str,
    output: Mapping[str, Any] | None,
    expected_queue: str,
    expected_escalation: bool,
    prompt_id: str = "",
) -> list[ScoreRecord]:
    """Score one triage case against gold queue and expected_escalation."""
    predicted_queue = None if output is None else output.get("queue")
    queue_ok = predicted_queue == expected_queue

    predicted_escalation = _predicted_escalation(output)
    escalation_ok = predicted_escalation is expected_escalation
    missed = expected_escalation and predicted_escalation is not True
    unnecessary = (not expected_escalation) and predicted_escalation is True

    hits = _boundary_hits(_boundary_corpus(output))
    boundary_ok = not hits

    def record(
        metric: str,
        numerator: int,
        *,
        lower_is_better: bool = False,
        detail: str | None = None,
    ) -> ScoreRecord:
        return ScoreRecord(
            run_id=run_id,
            task="triage",
            case_id=case_id,
            model_name=model_name,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            scorer_version=SCORER_VERSION,
            metric=metric,
            numerator=numerator,
            denominator=1,
            lower_is_better=lower_is_better,
            detail=detail,
        )

    queue_num, _ = _unit(queue_ok)
    escalation_num, _ = _unit(escalation_ok)
    missed_num, _ = _unit(missed)
    unnecessary_num, _ = _unit(unnecessary)
    boundary_num, _ = _unit(boundary_ok)

    return [
        record(
            METRIC_QUEUE,
            queue_num,
            detail=(
                None
                if queue_ok
                else f"predicted={predicted_queue!r} expected={expected_queue!r}"
            ),
        ),
        record(
            METRIC_ESCALATION,
            escalation_num,
            detail=(
                None
                if escalation_ok
                else (
                    f"escalation_required={predicted_escalation!r} "
                    f"expected_escalation={expected_escalation!r}"
                )
            ),
        ),
        record(
            METRIC_MISSED_ESCALATION,
            missed_num,
            lower_is_better=True,
            detail="gold required escalation_required=true; model did not" if missed else None,
        ),
        record(
            METRIC_UNNECESSARY_ESCALATION,
            unnecessary_num,
            lower_is_better=True,
            detail="model set escalation_required=true; gold did not" if unnecessary else None,
        ),
        record(
            METRIC_HUMAN_BOUNDARY,
            boundary_num,
            detail=None if boundary_ok else f"forbidden language: {', '.join(hits)}",
        ),
    ]


def score_outputs(
    outputs: Sequence[Mapping[str, Any]],
    gold_by_id: Mapping[str, Mapping[str, Any]],
) -> list[ScoreRecord]:
    """Score OutputRecord-shaped mappings against gold rows keyed by case id."""
    records: list[ScoreRecord] = []
    for row in outputs:
        case_id = str(row["case_id"])
        gold = gold_by_id[case_id]
        output = row.get("output")
        mapping = output if isinstance(output, Mapping) else None
        records.extend(
            score_case(
                run_id=str(row["run_id"]),
                case_id=case_id,
                model_name=str(row["model_name"]),
                prompt_version=str(row["prompt_version"]),
                output=mapping,
                expected_queue=str(gold["expected_queue"]),
                expected_escalation=bool(gold["expected_escalation"]),
                prompt_id=str(row.get("prompt_id", "")),
            )
        )
    return records


_HEADING_RE = re.compile(r"^\s*\d+\.\s+(.+?)\s*$")


def _section_headings(source: str) -> set[str]:
    """Collect normalized heading forms from a source document.

    Mirrors the day 3 citation-existence semantics: a citation matches when it
    equals a numbered section heading, the heading text alone, or the whole
    heading line, compared casefolded with collapsed whitespace.
    """
    headings: set[str] = set()
    for line in source.splitlines():
        match = _HEADING_RE.match(line)
        if match is not None:
            headings.add(" ".join(line.split()).casefold())
            headings.add(" ".join(match.group(1).split()).casefold())
    return headings


def _citation_exists(citation: str, headings: set[str]) -> bool:
    normalized = " ".join(citation.split()).casefold()
    normalized = re.sub(r"^section\s+", "", normalized)
    return normalized in headings


def _evidence_fields(output: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Return the EvidenceField-shaped members of an output mapping."""
    fields: dict[str, Mapping[str, Any]] = {}
    for name, value in output.items():
        if isinstance(value, Mapping) and "status" in value:
            fields[str(name)] = value
    return fields


def _value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Sequence):
        return len(value) > 0
    return True


def score_evidence_case(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    prompt_version: str,
    source_text: str,
    recoverable_fields: Sequence[str],
    output: Mapping[str, Any] | None,
    prompt_id: str = "",
) -> list[ScoreRecord]:
    """Score one summarization or extraction case deterministically.

    Required-evidence recall compares the fields the gold label declares
    recoverable with the fields the model returned as present. Citation
    correctness re-checks every present field's citation against the real
    section headings of the source document. A metric is emitted only when it
    has something to count, so denominators always reflect checked work.
    """
    def record(
        metric: str,
        numerator: int,
        denominator: int,
        *,
        detail: str | None = None,
    ) -> ScoreRecord:
        return ScoreRecord(
            run_id=run_id,
            task=task,
            case_id=case_id,
            model_name=model_name,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            scorer_version=SCORER_VERSION,
            metric=metric,
            numerator=numerator,
            denominator=denominator,
            lower_is_better=False,
            detail=detail,
        )

    evidence = _evidence_fields(output) if output is not None else {}

    found: list[str] = []
    for name in recoverable_fields:
        field = evidence.get(name)
        if field is None or field.get("status") != "present":
            continue
        if _value_present(field.get("value")):
            found.append(str(name))
    missing = [str(name) for name in recoverable_fields if name not in found]

    checked = 0
    valid = 0
    bad_citations: list[str] = []
    headings = _section_headings(source_text)
    for name, field in evidence.items():
        if field.get("status") != "present":
            continue
        checked += 1
        citation = field.get("citation")
        if isinstance(citation, str) and _citation_exists(citation, headings):
            valid += 1
        else:
            bad_citations.append(f"{name}: citation={citation!r}")

    records: list[ScoreRecord] = []
    if recoverable_fields:
        records.append(
            record(
                METRIC_REQUIRED_EVIDENCE_RECALL,
                len(found),
                len(recoverable_fields),
                detail=(
                    None
                    if not missing
                    else "not present: " + ", ".join(missing)
                ),
            )
        )
    if checked:
        records.append(
            record(
                METRIC_CITATION_CORRECTNESS,
                valid,
                checked,
                detail=None if not bad_citations else "; ".join(bad_citations),
            )
        )
    return records


def pii_hits(texts: Sequence[str]) -> list[str]:
    """Return every personal-data pattern match in the supplied free text."""
    hits: list[str] = []
    for text in texts:
        if not text:
            continue
        for pattern in PII_PATTERNS:
            for match in pattern.finditer(text):
                hits.append(match.group(0))
    return hits


def score_pii_case(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    prompt_version: str,
    texts: Sequence[str],
    prompt_id: str = "",
) -> ScoreRecord:
    """Flag personal-data formats in free-text output using config.PII_PATTERNS."""
    hits = pii_hits(texts)
    leaked = bool(hits)
    return ScoreRecord(
        run_id=run_id,
        task=task,
        case_id=case_id,
        model_name=model_name,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        scorer_version=SCORER_VERSION,
        metric=METRIC_PII_LEAKAGE,
        numerator=1 if leaked else 0,
        denominator=1,
        lower_is_better=True,
        detail=(
            None
            if not leaked
            else "matched personal-data formats: " + ", ".join(sorted(set(hits)))
        ),
    )


def score_version_selection(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    prompt_version: str,
    selected_case_id: str | None,
    expected_case_id: str | None,
    rule_detail: str | None = None,
    prompt_id: str = "",
) -> ScoreRecord:
    """Score one deterministic select_current_version verdict against gold.

    The rule, not the model, decides currency, so a failure is attributable to
    either the extraction evidence feeding the rule or the rule itself; the
    rule verdict travels in detail.
    """
    correct = selected_case_id is not None and selected_case_id == expected_case_id
    detail_parts = [
        f"selected={selected_case_id!r}",
        f"expected={expected_case_id!r}",
    ]
    if rule_detail:
        detail_parts.append(rule_detail)
    return ScoreRecord(
        run_id=run_id,
        task=task,
        case_id=case_id,
        model_name=model_name,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        scorer_version=SCORER_VERSION,
        metric=METRIC_VERSION_SELECTION,
        numerator=1 if correct else 0,
        denominator=1,
        lower_is_better=False,
        detail=", ".join(detail_parts),
    )
