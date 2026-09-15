"""Day 3 structured summarization and extraction run."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.schemas import (
    EvidenceField,
    PolicyExtraction,
    ProcedureSummary,
    schema_description,
)
from promptlab.structured import complete_structured, parse_and_validate
from promptlab.usage import CallRecord, append_record

SUMMARIZATION_IDS = tuple(f"S{index:02d}" for index in range(1, 13))
EXTRACTION_IDS = tuple(f"E{index:02d}" for index in range(1, 13))
MAX_OUTPUT_TOKENS = 1024
SUMMARIZE_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "summarize.v1.md"
EXTRACT_PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "extract.v2.md"
SUMMARIZATION_CASES_PATH = PROJECT_ROOT / "cases" / "summarization.jsonl"
EXTRACTION_CASES_PATH = PROJECT_ROOT / "cases" / "extraction.jsonl"
NOTES_PATH = PROJECT_ROOT / "docs" / "day3-notes.md"
RUN_DOCS_PATH = PROJECT_ROOT / "docs" / "day3-run.jsonl"

LEAKAGE_STRINGS = (
    "Larkspur",
    "Meadowcross",
    "Redhaven",
    "East Kestrel",
    "Build Note R1",
    "Schedule Z",
)


class RecordingAdapter:
    def __init__(self, inner: OllamaAdapter) -> None:
        self._inner = inner
        self.provider = inner.provider
        self.model_id = inner.model_id
        self.complete_calls = 0
        self.records: list[CallRecord] = []
        self.case_records: list[CallRecord] = []

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        self.complete_calls += 1
        result = self._inner.complete(request, run_id)
        self.records.extend(result.records)
        self.case_records.extend(result.records)
        return result

    def reset_case(self) -> None:
        self.complete_calls = 0
        self.case_records = []


def load_cases(path: Path, expected_ids: tuple[str, ...]) -> dict[str, str]:
    cases: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload: dict[str, Any] = json.loads(line)
        case_id = str(payload["id"])
        if case_id in expected_ids:
            cases[case_id] = str(payload["source"])
    missing = [case_id for case_id in expected_ids if case_id not in cases]
    if missing:
        raise KeyError(f"Missing cases in {path.name}: {', '.join(missing)}")
    return cases


def fill_prompt(template: str, schema: type[BaseModel], source: str) -> str:
    return template.replace("{schema_description}", schema_description(schema)).replace(
        "{document_text}", source
    )


def build_request(
    *,
    task: Literal["summarization", "extraction"],
    case_id: str,
    prompt_id: str,
    prompt_version: str,
    source: str,
    template: str,
    schema: type[BaseModel],
    temperature: float,
) -> CompletionRequest:
    return CompletionRequest(
        task=task,
        case_id=case_id,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        system=fill_prompt(template, schema, source),
        user_content=(
            "Return only the JSON object. "
            "Use only the keys listed in the schema description. "
            "Do not add keys for other document headings."
        ),
        temperature=temperature,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def classify_first_pass_error(text: str | None, schema: type[BaseModel]) -> str:
    if text is None or not text.strip():
        return "empty_or_truncated"
    try:
        parse_and_validate(
            CompletionResult(succeeded=True, text=text, error_type=None, records=[]),
            schema,
        )
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        message = str(exc).lower()
        if "json" in message:
            return "invalid_json"
        if "extra" in message:
            return "extra_field"
        if "field required" in message or "missing" in message:
            return "missing_field"
        return type(exc).__name__
    return "unknown"


def citation_failures(model: ProcedureSummary | PolicyExtraction, source: str) -> int:
    failures = 0
    field: EvidenceField
    for field in model.evidence_fields().values():
        if field.status != "present":
            continue
        citation = field.citation or ""
        if citation == "" or citation not in source:
            failures += 1
    return failures


def leakage_hits(model: PolicyExtraction) -> list[str]:
    blob = model.model_dump_json()
    return [marker for marker in LEAKAGE_STRINGS if marker in blob]


def run_task(
    *,
    adapter: RecordingAdapter,
    run_id: str,
    task: Literal["summarization", "extraction"],
    prompt_id: str,
    prompt_version: str,
    template: str,
    schema: type[BaseModel],
    cases: dict[str, str],
    case_ids: tuple[str, ...],
    temperature: float,
) -> dict[str, Any]:
    repaired = 0
    validated = 0
    first_errors: list[str] = []
    citation_fail_count = 0
    leak_count = 0
    outputs: dict[str, BaseModel] = {}

    for case_id in case_ids:
        adapter.reset_case()
        request = build_request(
            task=task,
            case_id=case_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            source=cases[case_id],
            template=template,
            schema=schema,
            temperature=temperature,
        )
        try:
            model = complete_structured(adapter, request, schema, run_id)
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            print(
                f"{task} {case_id}: failed after {adapter.complete_calls} call(s): {exc}",
                flush=True,
            )
        else:
            validated += 1
            outputs[case_id] = model
            if isinstance(model, ProcedureSummary | PolicyExtraction):
                citation_fail_count += citation_failures(model, cases[case_id])
            if isinstance(model, PolicyExtraction):
                leak_count += len(leakage_hits(model))
            print(
                f"{task} {case_id}: validated after {adapter.complete_calls} call(s)",
                flush=True,
            )
        if adapter.complete_calls > 1:
            repaired += 1
            first_text = adapter.case_records[0].response_text if adapter.case_records else None
            first_errors.append(classify_first_pass_error(first_text, schema))
        for record in adapter.case_records:
            append_record(record, run_id)

    return {
        "cases": len(case_ids),
        "validated": validated,
        "repaired": repaired,
        "repair_rate": repaired / len(case_ids),
        "citation_failures": citation_fail_count,
        "leakage": leak_count,
        "errors": first_errors,
        "outputs": outputs,
    }


def write_notes(
    *,
    run_id: str,
    model_id: str,
    summarization: dict[str, Any],
    extraction: dict[str, Any],
) -> None:
    error_names = Counter(summarization["errors"] + extraction["errors"])
    common = error_names.most_common(1)
    validated = summarization["validated"] + extraction["validated"]
    if common:
        error_label, error_count = common[0]
        error_sentence = (
            f"The most common validation error was {error_label} "
            f"({error_count} first-pass case(s))."
        )
        if validated == 0:
            change_sentence = (
                "The repair request now includes that Pydantic error text and tells the model "
                "to delete forbidden keys or add only the missing fields, then re-validates "
                "the JSON. No case produced a schema-valid object after the one allowed repair, "
                "so citation-existence and leakage counts stay 0."
            )
        else:
            change_sentence = (
                "The repair request now includes that Pydantic error text and tells the model "
                "to correct only those fields, then re-validates the JSON."
            )
    else:
        error_sentence = (
            "No case exhausted the repair loop; remaining issues were citation or leakage "
            "counts rather than unparseable JSON."
        )
        change_sentence = (
            "The first-pass prompt already asked for schema JSON, so the one repair attempt "
            "was only needed when the model added extra keys or omitted a required field."
        )

    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTES_PATH.write_text(
        (
            "# Day 3 notes\n\n"
            f"One `run_id` (`{run_id}`). One model (`{model_id}`). Temperature `0.0`. "
            "Prompts: `summarize.v1.md` and `extract.v2.md`. Local cost is `0.0`.\n\n"
            f"- Summarization repair rate: {summarization['repaired']}/{summarization['cases']} "
            f"({summarization['repair_rate']:.2f})\n"
            f"- Extraction repair rate: {extraction['repaired']}/{extraction['cases']} "
            f"({extraction['repair_rate']:.2f})\n"
            f"- Example leakage count: {extraction['leakage']}\n"
            f"- Citation-existence failure count: "
            f"{summarization['citation_failures'] + extraction['citation_failures']}\n\n"
            f"{error_sentence} {change_sentence}\n"
        ),
        encoding="utf-8",
    )


def copy_run_docs(run_id: str) -> None:
    source = Path("runs") / f"{run_id}.jsonl"
    RUN_DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_DOCS_PATH.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> None:
    settings = Settings.from_env()
    model_id = settings.models["mistral"].model_id
    adapter = RecordingAdapter(OllamaAdapter(model_id=model_id))
    run_id = str(uuid.uuid4())
    temperature = 0.0

    summarization = run_task(
        adapter=adapter,
        run_id=run_id,
        task="summarization",
        prompt_id="summarize",
        prompt_version="v1",
        template=SUMMARIZE_PROMPT_PATH.read_text(encoding="utf-8"),
        schema=ProcedureSummary,
        cases=load_cases(SUMMARIZATION_CASES_PATH, SUMMARIZATION_IDS),
        case_ids=SUMMARIZATION_IDS,
        temperature=temperature,
    )
    extraction = run_task(
        adapter=adapter,
        run_id=run_id,
        task="extraction",
        prompt_id="extract",
        prompt_version="v2",
        template=EXTRACT_PROMPT_PATH.read_text(encoding="utf-8"),
        schema=PolicyExtraction,
        cases=load_cases(EXTRACTION_CASES_PATH, EXTRACTION_IDS),
        case_ids=EXTRACTION_IDS,
        temperature=temperature,
    )

    write_notes(
        run_id=run_id,
        model_id=model_id,
        summarization=summarization,
        extraction=extraction,
    )
    copy_run_docs(run_id)
    print(f"run_id={run_id}", flush=True)
    print(f"wrote {NOTES_PATH} and {RUN_DOCS_PATH}", flush=True)


if __name__ == "__main__":
    main()
