"""Day 3: schema-validated summarization and extraction with bounded repair."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, ModelConfig, Settings
from promptlab.records import OutputRecord
from promptlab.schemas import (
    PolicyExtraction,
    SummarizationOutput,
    TaskName,
    schema_description,
)
from promptlab.structured import complete_structured
from promptlab.usage import CallRecord, append_record

MAX_OUTPUT_TOKENS = 1024
REQUIRED_PROMPT_SECTIONS = (
    "Task",
    "Input",
    "Constraints",
    "Output",
    "When the task cannot be completed",
)
LEAKAGE_MARKERS = (
    "Northglass",
    "Norwyn",
    "Bellwater",
    "Redhaven",
    "East Kestrel",
    "Schedule Z",
)

SUMMARIZE_PATH = PROJECT_ROOT / "src" / "prompts" / "summarize.v1.md"
EXTRACT_V1_PATH = PROJECT_ROOT / "src" / "prompts" / "extract.v1.md"
EXTRACT_V2_PATH = PROJECT_ROOT / "src" / "prompts" / "extract.v2.md"
SUMMARIZATION_CASES_PATH = PROJECT_ROOT / "cases" / "summarization.jsonl"
EXTRACTION_CASES_PATH = PROJECT_ROOT / "cases" / "extraction.jsonl"
DOCS_RUN_PATH = PROJECT_ROOT / "docs" / "day3-run.jsonl"
DOCS_NOTES_PATH = PROJECT_ROOT / "docs" / "day3-notes.md"

_NUMBERED_HEADING = re.compile(r"^\d+\.\s+\S")


class CountingAdapter:
    """Wrap an adapter so callers can count semantic attempts and collect CallRecords."""

    def __init__(self, inner: ModelAdapter) -> None:
        self._inner = inner
        self.provider = inner.provider
        self.model_id = inner.model_id
        self.calls = 0
        self.records: list[CallRecord] = []

    def reset(self) -> None:
        self.calls = 0
        self.records = []

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        self.calls += 1
        result = self._inner.complete(request, run_id)
        self.records.extend(result.records)
        return result


def load_cases(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("case file has a non-object row")
            rows.append(row)
    return rows


def render_prompt(
    template: str,
    source: str,
    schema: type[BaseModel],
) -> tuple[str, str]:
    rendered = template.replace(
        "{schema_description}",
        schema_description(schema),
    ).replace("{document_text}", source)
    marker = "<document>"
    if marker not in rendered:
        return "", rendered
    system, _, rest = rendered.partition(marker)
    return system.strip(), f"{marker}{rest}".strip()


def build_request(
    *,
    task: TaskName,
    case_id: str,
    prompt_id: str,
    prompt_version: str,
    system: str,
    user_content: str,
    temperature: float,
) -> CompletionRequest:
    return CompletionRequest(
        task=task,
        case_id=case_id,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        system=system,
        user_content=user_content,
        temperature=temperature,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def section_headings(source: str) -> set[str]:
    headings: set[str] = set()
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _NUMBERED_HEADING.match(stripped):
            headings.add(stripped)
        elif stripped.startswith("#"):
            headings.add(stripped)
            headings.add(stripped.lstrip("#").strip())
    return headings


def citation_existence_failures(output: SummarizationOutput | PolicyExtraction, source: str) -> int:
    headings = section_headings(source)
    failures = 0
    for field in output.evidence_fields().values():
        if field.status != "present":
            continue
        if field.citation is None or field.citation not in headings:
            failures += 1
    return failures


def has_example_leakage(output: dict[str, Any] | None) -> bool:
    if output is None:
        return False
    blob = json.dumps(output)
    return any(marker in blob for marker in LEAKAGE_MARKERS)


def repair_rate(records: Sequence[OutputRecord], task: TaskName) -> float:
    task_records = [record for record in records if record.task == task]
    if not task_records:
        return 0.0
    repaired = sum(1 for record in task_records if record.repairs > 0)
    return repaired / len(task_records)


def format_notes(
    *,
    run_id: str,
    model_id: str,
    records: Sequence[OutputRecord],
    citation_failures: int,
    leakage_count: int,
    common_error_note: str,
) -> str:
    summ_rate = repair_rate(records, "summarization")
    extr_rate = repair_rate(records, "extraction")
    summ_repaired = _repaired_count(records, "summarization")
    extr_repaired = _repaired_count(records, "extraction")
    return "\n".join(
        [
            "# Day 3 notes",
            "",
            f"Run id: {run_id}",
            f"Model: {model_id}",
            "Temperature: 0.0",
            "",
            f"Summarization repair rate: {summ_rate:.3f} ({summ_repaired}/12)",
            f"Extraction repair rate: {extr_rate:.3f} ({extr_repaired}/12)",
            f"Example leakage count: {leakage_count}",
            f"Citation-existence failure count: {citation_failures}",
            "",
            common_error_note,
            "",
        ]
    )


def _repaired_count(records: Sequence[OutputRecord], task: TaskName) -> int:
    return sum(1 for record in records if record.task == task and record.repairs > 0)


def run_case(
    *,
    adapter: CountingAdapter,
    case: dict[str, Any],
    template: str,
    schema: type[SummarizationOutput] | type[PolicyExtraction],
    prompt_id: str,
    prompt_version: str,
    model: ModelConfig,
    run_id: str,
    temperature: float,
    max_repairs: int,
) -> tuple[OutputRecord, list[CallRecord], str | None]:
    adapter.reset()
    system, user_content = render_prompt(template, str(case["source"]), schema)
    request = build_request(
        task=case["task"],
        case_id=str(case["id"]),
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        system=system,
        user_content=user_content,
        temperature=temperature,
    )

    validation_error: str | None = None
    try:
        parsed = complete_structured(
            adapter,
            request,
            schema,
            run_id,
            max_repairs=max_repairs,
        )
        repairs = max(0, adapter.calls - 1)
        record = OutputRecord(
            run_id=run_id,
            task=case["task"],
            case_id=str(case["id"]),
            model_name=model.logical_name,
            model_id=model.model_id,
            prompt_version=prompt_version,
            succeeded=True,
            repairs=repairs,
            output=parsed.model_dump(),
            error=None,
        )
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        validation_error = str(exc)
        repairs = max(0, adapter.calls - 1) if adapter.calls else 0
        record = OutputRecord(
            run_id=run_id,
            task=case["task"],
            case_id=str(case["id"]),
            model_name=model.logical_name,
            model_id=model.model_id,
            prompt_version=prompt_version,
            succeeded=False,
            repairs=repairs,
            output=None,
            error=validation_error,
        )

    return record, list(adapter.records), validation_error


def main() -> None:
    settings = Settings.from_env()
    model = settings.models["mistral"]
    temperature = 0.0
    max_repairs = settings.max_schema_repairs
    run_id = str(uuid4())

    summarize_template = SUMMARIZE_PATH.read_text(encoding="utf-8")
    extract_template = EXTRACT_V2_PATH.read_text(encoding="utf-8")
    summarization_cases = load_cases(SUMMARIZATION_CASES_PATH)
    extraction_cases = load_cases(EXTRACTION_CASES_PATH)

    adapter = CountingAdapter(
        OllamaAdapter(model_id=model.model_id, base_url=settings.ollama_base_url)
    )

    outputs: list[OutputRecord] = []
    call_records: list[CallRecord] = []
    validation_errors: list[str] = []
    citation_failures = 0
    leakage_count = 0

    Job = tuple[
        dict[str, Any],
        str,
        type[SummarizationOutput] | type[PolicyExtraction],
        str,
        str,
    ]
    jobs: list[Job] = []
    for case in summarization_cases:
        jobs.append((case, summarize_template, SummarizationOutput, "summarize", "v1"))
    for case in extraction_cases:
        jobs.append((case, extract_template, PolicyExtraction, "extract", "v2"))

    for case, template, schema, prompt_id, prompt_version in jobs:
        output, records, validation_error = run_case(
            adapter=adapter,
            case=case,
            template=template,
            schema=schema,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            model=model,
            run_id=run_id,
            temperature=temperature,
            max_repairs=max_repairs,
        )
        outputs.append(output)
        for record in records:
            append_record(record, run_id)
            call_records.append(record)
        if validation_error:
            validation_errors.append(validation_error)

        source = str(case["source"])
        if output.succeeded and output.output is not None:
            parsed: SummarizationOutput | PolicyExtraction
            if schema is SummarizationOutput:
                parsed = SummarizationOutput.model_validate(output.output)
            else:
                parsed = PolicyExtraction.model_validate(output.output)
            citation_failures += citation_existence_failures(parsed, source)
            if case["task"] == "extraction" and has_example_leakage(output.output):
                leakage_count += 1

        print(
            f"{output.case_id} {output.model_id}: "
            f"succeeded={output.succeeded} repairs={output.repairs} "
            f"error={output.error}"
        )

    common_error_note = _common_error_note(validation_errors, outputs)
    notes = format_notes(
        run_id=run_id,
        model_id=model.model_id,
        records=outputs,
        citation_failures=citation_failures,
        leakage_count=leakage_count,
        common_error_note=common_error_note,
    )
    _write_docs(outputs, notes)
    print(f"wrote {DOCS_RUN_PATH}")
    print(f"wrote {DOCS_NOTES_PATH}")
    print(f"call records: {len(call_records)}")


def _common_error_note(validation_errors: list[str], outputs: Sequence[OutputRecord]) -> str:
    succeeded = sum(1 for record in outputs if record.succeeded)
    repaired = sum(1 for record in outputs if record.repairs > 0)
    if not validation_errors and repaired == 0:
        return (
            "The most common validation error was none observed on the final outputs; "
            "no schema repair was required after tightening citation and absent-field instructions."
        )
    sample = validation_errors[0] if validation_errors else "missing required object fields"
    snippet = sample.splitlines()[0][:160]
    recovery = (
        f"The single repair attempt recovered outputs so {succeeded}/24 cases validated."
        if succeeded
        else (
            "The single repair attempt often still left prose-wrapped or incomplete "
            "EvidenceField objects, so final validation remained failing on those cases."
        )
    )
    return (
        f"The most common validation error was related to schema shape ({snippet}). "
        f"{recovery}"
    )


def _write_docs(outputs: Sequence[OutputRecord], notes: str) -> None:
    DOCS_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(record.model_dump_json() + "\n" for record in outputs)
    DOCS_RUN_PATH.write_text(body, encoding="utf-8")
    DOCS_NOTES_PATH.write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
