"""Day 3 runner: schema-validated summarization and extraction with bounded repair.

Runs prompts/summarize.v1.md over cases/summarization.jsonl and
prompts/extract.v2.md over cases/extraction.jsonl under one run_id, then
records outputs, leakage, and citation-existence evidence.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from promptlab.adapters.base import CompletionRequest
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.records import OutputRecord
from promptlab.records import append_record as append_output_record
from promptlab.schemas import (
    PolicyExtraction,
    SummarizationOutput,
    TaskName,
    schema_description,
)
from promptlab.structured import (
    StructuredCallTrace,
    StructuredCompletionError,
    complete_structured,
)
from promptlab.usage import append_record as append_call_record

LOGICAL_MODEL_KEY = "mistral"
MAX_OUTPUT_TOKENS = 1024
DOCUMENT_OPEN = "<document>"
EXPECTED_CASE_COUNT = 12
SUMMARIZE_PROMPT_ID = "summarize"
SUMMARIZE_PROMPT_VERSION = "v1"
EXTRACT_PROMPT_ID = "extract"
EXTRACT_PROMPT_VERSION = "v2"

SUMMARIZATION_CASES_PATH = PROJECT_ROOT / "cases" / "summarization.jsonl"
EXTRACTION_CASES_PATH = PROJECT_ROOT / "cases" / "extraction.jsonl"
SUMMARIZE_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "summarize.v1.md"
EXTRACT_V1_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "extract.v1.md"
EXTRACT_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "extract.v2.md"
EXAMPLE_PATHS = (
    PROJECT_ROOT / "examples" / "missing-required-field.md",
    PROJECT_ROOT / "examples" / "superseded.md",
)
RUNS_DIR = PROJECT_ROOT / "runs"
EVIDENCE_PATH = PROJECT_ROOT / "docs" / "day3-run.jsonl"
NOTES_PATH = PROJECT_ROOT / "docs" / "day3-notes.md"

_HEADING_RE = re.compile(r"^\s*\d+\.\s+(.+?)\s*$")


@dataclass(frozen=True)
class CaseOutcome:
    record: OutputRecord
    first_error: str | None


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case: dict[str, Any] = json.loads(line)
        cases.append(case)
    if len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError(
            f"expected {EXPECTED_CASE_COUNT} cases in {path.name}, got {len(cases)}"
        )
    return cases


def split_prompt(template: str, source: str, schema_text: str) -> tuple[str, str]:
    """Fill the template placeholders and split instructions from the marked document.

    Everything from the first <document> marker onward stays in user_content so
    sections that follow the document (constraints, examples) are preserved.
    """
    filled = template.replace("{schema_description}", schema_text)
    filled = filled.replace("{document_text}", source)
    marker_at = filled.find(DOCUMENT_OPEN)
    if marker_at < 0:
        raise ValueError("prompt template is missing document markers")
    return filled[:marker_at].rstrip(), filled[marker_at:]


def run_task(
    adapter: OllamaAdapter,
    run_id: str,
    cases: Sequence[dict[str, Any]],
    template: str,
    schema: type[BaseModel],
    task: TaskName,
    prompt_id: str,
    prompt_version: str,
    settings: Settings,
    outputs_path: Path,
) -> list[CaseOutcome]:
    schema_text = schema_description(schema)
    outcomes: list[CaseOutcome] = []
    for case in cases:
        case_id = str(case["id"])
        source = str(case["source"])
        system, user_content = split_prompt(template, source, schema_text)
        request = CompletionRequest(
            task=task,
            case_id=case_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            system=system,
            user_content=user_content,
            temperature=settings.temperature,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        trace = StructuredCallTrace()
        try:
            validated = complete_structured(
                adapter,
                request,
                schema,
                run_id,
                max_repairs=settings.max_schema_repairs,
                trace=trace,
            )
            record = OutputRecord(
                run_id=run_id,
                task=task,
                case_id=case_id,
                model_name=settings.models[LOGICAL_MODEL_KEY].logical_name,
                model_id=adapter.model_id,
                prompt_version=prompt_version,
                succeeded=True,
                repairs=trace.repairs,
                output=validated.model_dump(),
                error=None,
            )
            first_error = trace.first_error
        except StructuredCompletionError as exc:
            record = OutputRecord(
                run_id=run_id,
                task=task,
                case_id=case_id,
                model_name=settings.models[LOGICAL_MODEL_KEY].logical_name,
                model_id=adapter.model_id,
                prompt_version=prompt_version,
                succeeded=False,
                repairs=exc.trace.repairs,
                output=None,
                error=str(exc),
            )
            first_error = exc.trace.first_error
        for call in trace.records:
            append_call_record(call, run_id)
        append_output_record(outputs_path, record)
        outcomes.append(CaseOutcome(record=record, first_error=first_error))
        print(
            f"{task} {case_id} succeeded={record.succeeded} repairs={record.repairs}"
        )
    return outcomes


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _ngrams(tokens: Sequence[str], size: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def distinctive_example_ngrams(corpus_texts: Sequence[str]) -> set[tuple[str, ...]]:
    """Return example n-grams absent from every corpus text, at the largest useful size."""
    for size in (5, 4, 3):
        corpus: set[tuple[str, ...]] = set()
        for text in corpus_texts:
            corpus |= _ngrams(_tokens(text), size)
        example_grams: set[tuple[str, ...]] = set()
        for path in EXAMPLE_PATHS:
            example_grams |= _ngrams(_tokens(path.read_text(encoding="utf-8")), size)
        distinctive = example_grams - corpus
        if distinctive:
            return distinctive
    return set()


def contains_any_gram(text: str, grams: set[tuple[str, ...]]) -> bool:
    tokens = _tokens(text)
    size = len(next(iter(grams)))
    return any(
        tuple(tokens[i : i + size]) in grams for i in range(len(tokens) - size + 1)
    )


def leakage_case_ids(outcomes: Sequence[CaseOutcome], grams: set[tuple[str, ...]]) -> list[str]:
    if not grams:
        return []
    hits: list[str] = []
    for outcome in outcomes:
        if outcome.record.succeeded and outcome.record.output is not None:
            text = json.dumps(outcome.record.output)
            if contains_any_gram(text, grams):
                hits.append(outcome.record.case_id)
    return hits


def _section_headings(source: str) -> set[str]:
    headings: set[str] = set()
    for line in source.splitlines():
        match = _HEADING_RE.match(line)
        if match is not None:
            headings.add(" ".join(line.split()).casefold())
            headings.add(" ".join(match.group(1).split()).casefold())
    return headings


def citation_exists(citation: str, headings: set[str]) -> bool:
    normalized = " ".join(citation.split()).casefold()
    normalized = re.sub(r"^section\s+", "", normalized)
    return normalized in headings


def citation_failures(
    outcomes: Sequence[CaseOutcome],
    cases: Sequence[dict[str, Any]],
) -> list[str]:
    source_by_id = {str(case["id"]): str(case["source"]) for case in cases}
    failures: list[str] = []
    for outcome in outcomes:
        record = outcome.record
        if not record.succeeded or record.output is None:
            continue
        extraction = PolicyExtraction.model_validate(record.output)
        headings = _section_headings(source_by_id[record.case_id])
        for field_name, field in extraction.evidence_fields().items():
            if field.status != "present":
                continue
            if field.citation is None or not citation_exists(field.citation, headings):
                failures.append(f"{record.case_id} {field_name}: citation={field.citation!r}")
    return failures


def _error_signature(first_error: str) -> str:
    match = re.search(r"\[type=([a-z_]+)", first_error)
    if match is not None:
        return match.group(1)
    return " ".join(first_error.split())[:200]


def _repair_rate(outcomes: Sequence[CaseOutcome]) -> tuple[int, int, str]:
    repaired = sum(1 for outcome in outcomes if outcome.record.repairs >= 1)
    total = len(outcomes)
    percent = f"{(repaired / total * 100):.1f}" if total else "0.0"
    return repaired, total, percent


def render_notes(
    settings: Settings,
    model_id: str,
    summarization: Sequence[CaseOutcome],
    extraction: Sequence[CaseOutcome],
    leakage: Sequence[str],
    citation_failure_lines: Sequence[str],
) -> str:
    sum_repaired, sum_total, sum_pct = _repair_rate(summarization)
    ext_repaired, ext_total, ext_pct = _repair_rate(extraction)

    first_failures = [
        (outcome, error)
        for outcome in [*summarization, *extraction]
        if (error := outcome.first_error) is not None
    ]
    recovered = sum(
        1 for outcome, _ in first_failures if outcome.record.succeeded
    )
    signature_counts = Counter(error for _, error in first_failures)

    lines = [
        "# Day 3 notes: prompts that return validated objects",
        "",
        (
            f"Model: {model_id} (logical name {LOGICAL_MODEL_KEY}), temperature "
            f"{settings.temperature}, one run_id. Summarization ran "
            f"prompts/summarize.v1.md over {sum_total} summarization cases; "
            f"extraction ran prompts/extract.v2.md over {ext_total} extraction "
            "cases. A repair attempt means one bounded semantic repair request "
            "carrying the validation error; transport retries stay inside the "
            "adapter and are not counted."
        ),
        "",
        "## Metrics",
        "",
        f"- Summarization repair rate: {sum_repaired}/{sum_total} ({sum_pct}%)",
        f"- Extraction repair rate: {ext_repaired}/{ext_total} ({ext_pct}%)",
        (
            f"- Example leakage count: {len(leakage)} of {ext_total} extraction "
            "outputs contained n-grams distinctive to the two few-shot example "
            "documents" + (f" ({', '.join(leakage)})" if leakage else "")
        ),
        (
            f"- Citation-existence failures: {len(citation_failure_lines)} evidence "
            'fields with status "present" whose citation does not match a real '
            "section heading in the case source"
        ),
        "",
        "## Most common validation error",
        "",
    ]
    if first_failures:
        signature, count = signature_counts.most_common(1)[0]
        lines.append(
            f"The most common first-pass validation failure was the "
            f"{signature!r} error class, seen in {count} of "
            f"{len(first_failures)} first attempts that failed validation."
        )
        lines.append(
            f"The repair request repeated the delimited document together with the "
            f"previous response and the validation error and asked the model to "
            f"correct only that concern; this recovered {recovered} of "
            f"{len(first_failures)} first-pass failures."
        )
    else:
        lines.append(
            "No first-pass validation failures occurred, so no repair was needed."
        )
    if citation_failure_lines:
        lines.extend(["", "## Citation failures", ""])
        lines.extend(f"- {line}" for line in citation_failure_lines)
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    settings = Settings.from_env()
    run_id = str(uuid4())
    model_id = settings.models[LOGICAL_MODEL_KEY].model_id
    adapter = OllamaAdapter(model_id=model_id)

    summarization_cases = load_cases(SUMMARIZATION_CASES_PATH)
    extraction_cases = load_cases(EXTRACTION_CASES_PATH)
    summarize_template = SUMMARIZE_PROMPT_PATH.read_text(encoding="utf-8")
    extract_template = EXTRACT_PROMPT_PATH.read_text(encoding="utf-8")

    outputs_path = RUNS_DIR / f"{run_id}.outputs.jsonl"
    outputs_path.parent.mkdir(parents=True, exist_ok=True)

    summarization = run_task(
        adapter,
        run_id,
        summarization_cases,
        summarize_template,
        SummarizationOutput,
        "summarization",
        SUMMARIZE_PROMPT_ID,
        SUMMARIZE_PROMPT_VERSION,
        settings,
        outputs_path,
    )
    extraction = run_task(
        adapter,
        run_id,
        extraction_cases,
        extract_template,
        PolicyExtraction,
        "extraction",
        EXTRACT_PROMPT_ID,
        EXTRACT_PROMPT_VERSION,
        settings,
        outputs_path,
    )

    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(outputs_path, EVIDENCE_PATH)

    corpus = [str(case["source"]) for case in [*summarization_cases, *extraction_cases]]
    corpus.append(SUMMARIZE_PROMPT_PATH.read_text(encoding="utf-8"))
    corpus.append(EXTRACT_V1_PROMPT_PATH.read_text(encoding="utf-8"))
    grams = distinctive_example_ngrams(corpus)
    leakage = leakage_case_ids(extraction, grams)
    failures = citation_failures(extraction, extraction_cases)

    notes = render_notes(settings, model_id, summarization, extraction, leakage, failures)
    NOTES_PATH.write_text(notes, encoding="utf-8")

    print(f"run_id={run_id}")
    print(f"call_records={RUNS_DIR / (run_id + '.jsonl')}")
    print(f"outputs={outputs_path}")
    print(f"evidence={EVIDENCE_PATH}")
    print(f"notes={NOTES_PATH}")


if __name__ == "__main__":
    main()
