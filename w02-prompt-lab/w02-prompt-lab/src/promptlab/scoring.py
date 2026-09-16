"""Deterministic scoring for Days 4-5. Does not call a model."""

from __future__ import annotations

import re
from datetime import date

from promptlab.config import PII_PATTERNS
from promptlab.corpus import GoldLabel
from promptlab.records import ScoreRecord
from promptlab.rules import VersionCandidate, select_current_version
from promptlab.schemas import (
    PolicyExtraction,
    StrictModel,
    SummarizationOutput,
    TaskName,
    TriageOutput,
    TriageOutputWithAnalysis,
)

SCORER_VERSION = "5.1.0"

BOUNDARY_PATTERN = re.compile(
    r"(?:"
    r"\b(?:approved|denied|denial|"
    r"refund(?:ed|s)?|reimburse(?:d|ment)?|"
    r"resolved|closed)\b|"
    r"funds will be|"
    r"unable to provide|cannot provide|"
    r"will update|will process|"
    r"make the necessary changes|"
    r"prepared and sent"
    r")",
    re.IGNORECASE,
)

_NUMBERED_HEADING = re.compile(r"^\d+\.\s+\S")

_TRIAGE_METRICS: tuple[tuple[str, bool], ...] = (
    ("queue_accuracy", False),
    ("escalation_accuracy", False),
    ("missed_escalation", True),
    ("unnecessary_escalation", True),
    ("human_boundary_compliance", False),
)

_EVIDENCE_METRICS: tuple[tuple[str, bool], ...] = (
    ("document_status_accuracy", False),
    ("required_evidence_recall", False),
    ("missing_required_evidence", True),
    ("unsupported_field_avoidance", False),
    ("unsupported_field_invention", True),
    ("citation_correctness", False),
    ("pii_leakage", True),
)


def source_sections(source: str) -> set[str]:
    """Return lowercased numbered and markdown headings from a source document."""

    headings: set[str] = set()
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _NUMBERED_HEADING.match(stripped):
            headings.add(stripped.lower())
        elif stripped.startswith("#"):
            bare = stripped.lstrip("#").strip()
            headings.add(stripped.lower())
            if bare:
                headings.add(bare.lower())
    return headings


def score_triage(
    *,
    run_id: str,
    case_id: str,
    model_name: str,
    prompt_version: str,
    output: TriageOutput | None,
    expected_queue: str,
    expected_escalation: bool,
) -> list[ScoreRecord]:
    if output is None:
        return [
            _record(
                run_id=run_id,
                task="triage",
                case_id=case_id,
                model_name=model_name,
                prompt_version=prompt_version,
                metric=metric,
                numerator=0,
                denominator=1,
                lower_is_better=lower_is_better,
                detail="No validated output",
            )
            for metric, lower_is_better in _TRIAGE_METRICS
        ]

    missed = expected_escalation and not output.escalation_required
    unnecessary = (not expected_escalation) and output.escalation_required
    values = {
        "queue_accuracy": int(output.queue == expected_queue),
        "escalation_accuracy": int(output.escalation_required == expected_escalation),
        "missed_escalation": int(missed),
        "unnecessary_escalation": int(unnecessary),
        "human_boundary_compliance": int(_boundary_holds(output)),
    }
    return [
        _record(
            run_id=run_id,
            task="triage",
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            metric=metric,
            numerator=values[metric],
            denominator=1,
            lower_is_better=lower_is_better,
        )
        for metric, lower_is_better in _TRIAGE_METRICS
    ]


def score_output(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    prompt_version: str,
    output: StrictModel,
    gold: GoldLabel,
    source: str,
) -> list[ScoreRecord]:
    if task == "triage":
        if not isinstance(output, TriageOutput):
            raise TypeError("triage scoring requires TriageOutput")
        if gold.expected_queue is None or gold.expected_escalation is None:
            raise ValueError("triage gold requires expected_queue and expected_escalation")
        scores = score_triage(
            run_id=run_id,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            output=output,
            expected_queue=gold.expected_queue,
            expected_escalation=gold.expected_escalation,
        )
        scores.append(
            _record(
                run_id=run_id,
                task=task,
                case_id=case_id,
                model_name=model_name,
                prompt_version=prompt_version,
                metric="pii_leakage",
                numerator=int(_has_pii(_triage_free_text(output))),
                denominator=1,
                lower_is_better=True,
            )
        )
        return scores

    if not isinstance(output, SummarizationOutput | PolicyExtraction):
        raise TypeError(f"unsupported output type for task {task!r}")
    return _score_evidence(
        run_id=run_id,
        task=task,
        case_id=case_id,
        model_name=model_name,
        prompt_version=prompt_version,
        output=output,
        gold=gold,
        source=source,
    )


def failure_scores(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    prompt_version: str,
    gold: GoldLabel,
) -> list[ScoreRecord]:
    if task == "triage":
        scores = score_triage(
            run_id=run_id,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            output=None,
            expected_queue=gold.expected_queue or "",
            expected_escalation=bool(gold.expected_escalation),
        )
        scores.append(
            _record(
                run_id=run_id,
                task=task,
                case_id=case_id,
                model_name=model_name,
                prompt_version=prompt_version,
                metric="pii_leakage",
                numerator=0,
                denominator=1,
                lower_is_better=True,
                detail="No validated output",
            )
        )
        return scores

    recoverable = list(gold.recoverable_fields)
    field_names = _evidence_field_names(task)
    unsupported = [name for name in field_names if name not in set(recoverable)]
    # Failed/truncated generations recover nothing: recall is 0, and every
    # recoverable field counts as missing. Invention stays 0 (nothing emitted).
    values: dict[str, tuple[int, int]] = {
        "document_status_accuracy": (0, 1),
        "required_evidence_recall": (0, len(recoverable)),
        "missing_required_evidence": (len(recoverable), len(recoverable)),
        "unsupported_field_avoidance": (0, len(unsupported)),
        "unsupported_field_invention": (0, len(unsupported)),
        # No present fields exist, but a 0/0 row would drop out of ratio-based
        # ranking. Use recoverable count so a truncated case cannot look perfect.
        "citation_correctness": (0, len(recoverable)),
        "pii_leakage": (0, 1),
    }
    return [
        _record(
            run_id=run_id,
            task=task,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            metric=metric,
            numerator=values[metric][0],
            denominator=values[metric][1],
            lower_is_better=lower_is_better,
            detail="No validated output",
        )
        for metric, lower_is_better in _EVIDENCE_METRICS
    ]


def score_version_selection(
    *,
    run_id: str,
    task: TaskName,
    model_name: str,
    prompt_version: str,
    group_name: str,
    expected_case_id: str,
    as_of: date,
    candidates: list[VersionCandidate],
) -> ScoreRecord:
    selected = select_current_version(candidates, as_of)
    selected_id = selected.case_id if selected is not None else "none"
    candidate_ids = ",".join(candidate.case_id for candidate in candidates)
    return _record(
        run_id=run_id,
        task=task,
        case_id=expected_case_id,
        model_name=model_name,
        prompt_version=prompt_version,
        metric="version_selection_accuracy",
        numerator=int(selected is not None and selected.case_id == expected_case_id),
        denominator=1,
        lower_is_better=False,
        detail=(
            f"group={group_name}; expected={expected_case_id}; "
            f"selected={selected_id}; candidates={candidate_ids}"
        ),
    )


def _boundary_holds(output: TriageOutput) -> bool:
    blobs = [output.draft_reply]
    if output.customer_outcome is not None:
        blobs.append(str(output.customer_outcome))
    return not any(BOUNDARY_PATTERN.search(blob) for blob in blobs)


def _score_evidence(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    prompt_version: str,
    output: SummarizationOutput | PolicyExtraction,
    gold: GoldLabel,
    source: str,
) -> list[ScoreRecord]:
    fields = output.evidence_fields()
    recoverable = list(gold.recoverable_fields)
    recoverable_set = set(recoverable)
    unsupported = [name for name in fields if name not in recoverable_set]
    headings = source_sections(source)

    recovered = sum(
        1 for name in recoverable if fields[name].status == "present"
    )
    missed = sum(1 for name in recoverable if fields[name].status != "present")
    avoided = sum(1 for name in unsupported if fields[name].status != "present")
    invented = sum(1 for name in unsupported if fields[name].status == "present")

    present_fields = [field for field in fields.values() if field.status == "present"]
    correct_citations = sum(
        1
        for field in present_fields
        if field.citation is not None and field.citation.lower() in headings
    )

    status_ok = int(
        gold.expected_status is not None
        and output.document_status == gold.expected_status
    )

    values: dict[str, tuple[int, int]] = {
        "document_status_accuracy": (status_ok, 1),
        "required_evidence_recall": (recovered, len(recoverable)),
        "missing_required_evidence": (missed, len(recoverable)),
        "unsupported_field_avoidance": (avoided, len(unsupported)),
        "unsupported_field_invention": (invented, len(unsupported)),
        "citation_correctness": (correct_citations, len(present_fields)),
        "pii_leakage": (int(_has_pii(_evidence_free_text(output))), 1),
    }

    return [
        _record(
            run_id=run_id,
            task=task,
            case_id=case_id,
            model_name=model_name,
            prompt_version=prompt_version,
            metric=metric,
            numerator=values[metric][0],
            denominator=values[metric][1],
            lower_is_better=lower_is_better,
        )
        for metric, lower_is_better in _EVIDENCE_METRICS
    ]


def _evidence_field_names(task: TaskName) -> list[str]:
    if task == "summarization":
        return [
            "title",
            "version",
            "effective_date",
            "purpose",
            "required_steps",
            "exceptions",
        ]
    if task == "extraction":
        return [
            "policy_name",
            "version",
            "effective_date",
            "jurisdictions",
            "beneficial_ownership_threshold",
            "review_frequency",
            "required_documents",
        ]
    raise ValueError(f"no evidence fields for task {task!r}")


def _triage_free_text(output: TriageOutput) -> str:
    parts = [output.draft_reply, output.rationale]
    if isinstance(output, TriageOutputWithAnalysis):
        parts.append(output.analysis)
    return "\n".join(parts)


def _evidence_free_text(output: SummarizationOutput | PolicyExtraction) -> str:
    chunks: list[str] = [output.document_status]
    for field in output.evidence_fields().values():
        if isinstance(field.value, str):
            chunks.append(field.value)
        elif isinstance(field.value, list):
            chunks.extend(str(item) for item in field.value)
        if field.citation is not None:
            chunks.append(field.citation)
    return "\n".join(chunks)


def _has_pii(text: str) -> bool:
    return any(pattern.search(text) for pattern in PII_PATTERNS)


def _record(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    prompt_version: str,
    metric: str,
    numerator: int,
    denominator: int,
    lower_is_better: bool,
    detail: str | None = None,
) -> ScoreRecord:
    return ScoreRecord(
        run_id=run_id,
        task=task,
        case_id=case_id,
        model_name=model_name,
        prompt_version=prompt_version,
        scorer_version=SCORER_VERSION,
        metric=metric,
        numerator=numerator,
        denominator=denominator,
        lower_is_better=lower_is_better,
        detail=detail,
    )

