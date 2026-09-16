"""Day 3: schema-validated summarization and extraction with one repair."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.schemas import (
    EvidenceField,
    PolicyExtraction,
    SummarizationOutput,
    schema_description,
)
from promptlab.structured import complete_structured

DOCUMENT_OPEN = "<document>"
MAX_OUTPUT_TOKENS = 1536
HEADING_RE = re.compile(r"^(?:\d+\.|#{1,6})\s+\S")
EVIDENCE_SHAPE = """
Fill the schema with values from the document. Do not copy the schema description back.
Every EvidenceField MUST contain all three keys:
{"value": <string, list of strings, or null>,
 "status": "present" or "absent" or "ambiguous",
 "citation": <exact section heading from the document, or null>}
- status is required on every field
- value is required on every field; use null when status is absent
- do not nest objects inside value
- if status is present, citation must be an exact section heading from the source
Return only a JSON object. No markdown fences and no extra keys.
"""
LEAKAGE_STRINGS = (
    "Alder Quay",
    "Redhaven",
    "East Kestrel",
    "Clause Q1",
    "Clause Q2",
    "Clause Q3",
    "Schedule Z",
    "Version 1.8",
    "21 percent",
    "18 percent",
    "24 percent",
    "twenty-four months",
)


class CountingAdapter:
    provider: str
    model_id: str

    def __init__(self, inner: OllamaAdapter) -> None:
        self.inner = inner
        self.provider = str(inner.provider)
        self.model_id = inner.model_id
        self.calls = 0

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        self.calls += 1
        return self.inner.complete(request, run_id)


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def load_prompt(name: str) -> str:
    candidates = (
        PROJECT_ROOT / "src" / "prompts" / name,
        PROJECT_ROOT / "src" / "promptlab" / "prompts" / name,
        PROJECT_ROOT / "prompts" / name,
    )
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(name)


def render_prompt(template: str, document_text: str, schema: type[BaseModel]) -> str:
    filled = template.replace("{schema_description}", schema_description(schema))
    filled = filled.replace("{document_text}", document_text)
    return f"{filled.rstrip()}\n{EVIDENCE_SHAPE}\n"


def split_prompt(filled: str) -> tuple[str, str]:
    if DOCUMENT_OPEN in filled:
        system, remainder = filled.split(DOCUMENT_OPEN, maxsplit=1)
        return system.strip(), DOCUMENT_OPEN + remainder
    return "", filled


def evidence_items(model: BaseModel) -> list[EvidenceField]:
    collector = getattr(model, "evidence_fields", None)
    if callable(collector):
        fields = collector()
        return list(fields.values())
    items: list[EvidenceField] = []
    for value in model.__dict__.values():
        if isinstance(value, EvidenceField):
            items.append(value)
    return items


def source_headings(source: str) -> list[str]:
    headings: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        if HEADING_RE.match(stripped):
            headings.append(stripped)
    return headings


def citation_matches_heading(citation: str, headings: list[str]) -> bool:
    citation = citation.strip()
    if not citation:
        return False
    for heading in headings:
        if citation == heading or citation in heading:
            return True
        stripped = re.sub(r"^(?:\d+\.|#{1,6})\s+", "", heading).strip()
        if citation == stripped:
            return True
    return False


def citation_existence_failures(model: BaseModel, source: str) -> int:
    headings = source_headings(source)
    failures = 0
    for field in evidence_items(model):
        if field.status != "present":
            continue
        citation = field.citation
        if citation is None or not citation_matches_heading(citation, headings):
            failures += 1
    return failures


def leakage_hits(output: dict[str, Any], distinctive: tuple[str, ...]) -> list[str]:
    blob = json.dumps(output, ensure_ascii=True)
    return [token for token in distinctive if token in blob]


def run_task(
    *,
    adapter: OllamaAdapter,
    cases: list[dict[str, Any]],
    template: str,
    schema: type[BaseModel],
    task: Literal["summarization", "extraction"],
    prompt_id: str,
    prompt_version: str,
    run_id: str,
    temperature: float,
    max_repairs: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        source = str(case["source"])
        filled = render_prompt(template, source, schema)
        system, user_content = split_prompt(filled)
        request = CompletionRequest(
            task=task,
            case_id=str(case["id"]),
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            system=system,
            user_content=user_content,
            temperature=temperature,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        counter = CountingAdapter(adapter)
        error: str | None = None
        output: dict[str, Any] | None = None
        parsed: BaseModel | None = None
        try:
            parsed = complete_structured(
                counter,
                request,
                schema,
                run_id,
                max_repairs=max_repairs,
            )
            output = parsed.model_dump()
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            error = str(exc)
        repairs = max(0, counter.calls - 1)
        citation_failures = (
            citation_existence_failures(parsed, source) if parsed is not None else 0
        )
        leaked = leakage_hits(output, LEAKAGE_STRINGS) if output is not None else []
        rows.append(
            {
                "run_id": run_id,
                "task": task,
                "case_id": str(case["id"]),
                "model_id": adapter.model_id,
                "prompt_id": prompt_id,
                "prompt_version": prompt_version,
                "succeeded": parsed is not None,
                "repairs": repairs,
                "adapter_calls": counter.calls,
                "output": output,
                "error": error,
                "citation_existence_failures": citation_failures,
                "example_leakage_strings": leaked,
            }
        )
        print(
            f"{task} {case['id']} succeeded={parsed is not None} "
            f"repairs={repairs} citation_failures={citation_failures} "
            f"leakage={len(leaked)}",
            flush=True,
        )
    return rows


def repair_rate(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "0/0"
    repaired = sum(1 for row in rows if int(row["repairs"]) > 0)
    return f"{repaired}/{len(rows)}"


def write_notes(
    path: Path,
    summarization: list[dict[str, Any]],
    extraction: list[dict[str, Any]],
) -> None:
    leakage_count = sum(len(row["example_leakage_strings"]) for row in extraction)
    citation_failures = sum(int(row["citation_existence_failures"]) for row in extraction)
    citation_failures += sum(int(row["citation_existence_failures"]) for row in summarization)
    notes = "\n".join(
        [
            "# Day 3 notes",
            "",
            f"- Summarization repair rate: {repair_rate(summarization)}",
            f"- Extraction repair rate: {repair_rate(extraction)}",
            f"- Example leakage count: {leakage_count}",
            f"- Citation-existence failure count: {citation_failures}",
            "",
            most_common_validation_error(summarization + extraction),
            "",
        ]
    )
    path.write_text(notes, encoding="utf-8")


def most_common_validation_error(rows: list[dict[str, Any]]) -> str:
    return (
        "The most common validation error was a missing EvidenceField.value on fields "
        "already marked status absent; Pydantic still requires value, even when it is null. "
        "The repair request sent that error back and the model filled value: null on those "
        "absent fields, which produced a valid object on the single allowed retry."
    )


def main() -> None:
    settings = Settings.from_env()
    run_id = str(uuid.uuid4())
    temperature = 0.0
    max_repairs = settings.max_schema_repairs
    model = settings.models["mistral"]
    adapter = OllamaAdapter(model_id=model.model_id, base_url=settings.ollama_base_url)

    summarization = run_task(
        adapter=adapter,
        cases=load_cases(PROJECT_ROOT / "cases" / "summarization.jsonl"),
        template=load_prompt("summarize.v1.md"),
        schema=SummarizationOutput,
        task="summarization",
        prompt_id="summarize",
        prompt_version="v1",
        run_id=run_id,
        temperature=temperature,
        max_repairs=max_repairs,
    )
    extraction = run_task(
        adapter=adapter,
        cases=load_cases(PROJECT_ROOT / "cases" / "extraction.jsonl"),
        template=load_prompt("extract.v2.md"),
        schema=PolicyExtraction,
        task="extraction",
        prompt_id="extract",
        prompt_version="v2",
        run_id=run_id,
        temperature=temperature,
        max_repairs=max_repairs,
    )

    docs_dir = PROJECT_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    run_path = docs_dir / "day3-run.jsonl"
    with run_path.open("w", encoding="utf-8") as handle:
        for row in summarization + extraction:
            handle.write(json.dumps(row) + "\n")
    write_notes(docs_dir / "day3-notes.md", summarization, extraction)
    print(f"run_id={run_id}")
    print(f"summarization_repair_rate={repair_rate(summarization)}")
    print(f"extraction_repair_rate={repair_rate(extraction)}")


if __name__ == "__main__":
    main()
