"""Day 5 evaluation harness: three tasks, both configured local models."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.prompts import load, render_user
from promptlab.records import OutputRecord, ScoreRecord
from promptlab.records import append_record as append_score
from promptlab.schemas import (
    PolicyExtraction,
    SummarizationOutput,
    TaskName,
    TriageOutput,
    schema_description,
)
from promptlab.scoring import (
    load_gold,
    score_evidence_output,
    score_triage_output,
    score_version_selection,
)
from promptlab.structured import complete_structured
from promptlab.usage import CallRecord, append_record

MAX_OUTPUT_TOKENS = 1024
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
RUN_DOCS_PATH = PROJECT_ROOT / "docs" / "day5-run.jsonl"
SCORE_DOCS_PATH = PROJECT_ROOT / "docs" / "day5-scores.jsonl"
TASK_ORDER: tuple[TaskName, ...] = ("summarization", "extraction", "triage")


@dataclass(frozen=True)
class TaskSpec:
    task: TaskName
    prompt_id: str
    prompt_version: str
    schema: type[BaseModel]
    case_prefix: str

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(f"{self.case_prefix}{index:02d}" for index in range(1, 13))

    @property
    def cases_path(self) -> Path:
        return PROJECT_ROOT / "cases" / f"{self.task}.jsonl"


TASK_SPECS: dict[TaskName, TaskSpec] = {
    "summarization": TaskSpec(
        task="summarization",
        prompt_id="summarize",
        prompt_version="v1",
        schema=SummarizationOutput,
        case_prefix="S",
    ),
    "extraction": TaskSpec(
        task="extraction",
        prompt_id="extract",
        prompt_version="v2",
        schema=PolicyExtraction,
        case_prefix="E",
    ),
    "triage": TaskSpec(
        task="triage",
        prompt_id="triage",
        prompt_version="v1",
        schema=TriageOutput,
        case_prefix="T",
    ),
}


class RecordingAdapter:
    def __init__(self, inner: ModelAdapter) -> None:
        self._inner = inner
        self.provider = inner.provider
        self.model_id = inner.model_id
        self.complete_calls = 0
        self.case_records: list[CallRecord] = []

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        self.complete_calls += 1
        result = self._inner.complete(request, run_id)
        self.case_records.extend(result.records)
        return result

    def reset_case(self) -> None:
        self.complete_calls = 0
        self.case_records = []


def call_log_path(run_id: str) -> Path:
    return Path("runs") / f"{run_id}.jsonl"


def load_cases(path: Path, expected_ids: Sequence[str]) -> dict[str, str]:
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


def build_parser(settings: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run summarization, extraction, and triage against configured local models.",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Stable identifier shared by call and score records",
    )
    parser.add_argument(
        "--task",
        choices=list(TASK_SPECS),
        help="Run one task instead of all three",
    )
    parser.add_argument(
        "--model",
        choices=list(settings.models),
        help="Run one configured logical model instead of both",
    )
    parser.add_argument("--limit", type=int, help="Limit cases per task for a smoke run")
    return parser


def planned_evaluations(
    tasks: Sequence[TaskName],
    model_names: Sequence[str],
    limit: int | None,
) -> int:
    cases_per_task = 12 if limit is None else limit
    return len(tasks) * len(model_names) * cases_per_task


def _build_request(
    *,
    spec: TaskSpec,
    case_id: str,
    source: str,
    temperature: float,
) -> CompletionRequest:
    template = load(spec.prompt_id, spec.prompt_version)
    variables = {"schema_description": schema_description(spec.schema)}
    return CompletionRequest(
        task=spec.task,
        case_id=case_id,
        prompt_id=spec.prompt_id,
        prompt_version=spec.prompt_version,
        system=template.system,
        user_content=render_user(template, variables, source),
        temperature=temperature,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def _score_case(
    *,
    spec: TaskSpec,
    output_record: OutputRecord,
    gold: dict[str, Any],
    source: str,
) -> list[ScoreRecord]:
    if spec.task == "triage":
        return score_triage_output(output_record=output_record, gold=gold)
    return score_evidence_output(
        output_record=output_record,
        gold=gold,
        source=source,
    )


def evaluate(
    *,
    run_id: str,
    tasks: Sequence[TaskName],
    model_names: Sequence[str],
    settings: Settings,
    adapter_factory: Callable[[str], ModelAdapter] | None = None,
    limit: int | None = None,
    score_path: Path = SCORE_DOCS_PATH,
    run_docs_path: Path = RUN_DOCS_PATH,
) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise SystemExit("--run-id must start with a letter or number and use '.', '_', or '-'")
    if limit is not None and limit < 1:
        raise SystemExit("--limit must be at least 1")

    source_log = call_log_path(run_id)
    if source_log.exists():
        raise SystemExit(f"Run already exists: {source_log}")

    factory = adapter_factory or (lambda model_id: OllamaAdapter(model_id=model_id))
    if score_path.exists():
        score_path.unlink()

    for task in tasks:
        spec = TASK_SPECS[task]
        case_ids = spec.case_ids[:limit]
        cases = load_cases(spec.cases_path, case_ids)
        gold = load_gold(spec.task)
        for model_name in model_names:
            model = settings.models[model_name]
            adapter = RecordingAdapter(factory(model.model_id))
            outputs: list[OutputRecord] = []
            for case_id in case_ids:
                adapter.reset_case()
                request = _build_request(
                    spec=spec,
                    case_id=case_id,
                    source=cases[case_id],
                    temperature=settings.temperature,
                )
                output: dict[str, Any] | None = None
                error: str | None = None
                try:
                    parsed = complete_structured(
                        adapter,
                        request,
                        spec.schema,
                        run_id,
                        max_repairs=settings.max_schema_repairs,
                    )
                except (ValueError, ValidationError, json.JSONDecodeError) as exc:
                    error = str(exc)
                    print(
                        f"{spec.prompt_id}.{spec.prompt_version} {model_name} {case_id}: "
                        f"failed after {adapter.complete_calls} call(s)",
                        flush=True,
                    )
                else:
                    output = parsed.model_dump(mode="json")
                    print(
                        f"{spec.prompt_id}.{spec.prompt_version} {model_name} {case_id}: "
                        f"validated after {adapter.complete_calls} call(s)",
                        flush=True,
                    )
                output_record = OutputRecord(
                    run_id=run_id,
                    task=spec.task,
                    case_id=case_id,
                    model_name=model_name,
                    model_id=model.model_id,
                    prompt_id=spec.prompt_id,
                    prompt_version=spec.prompt_version,
                    succeeded=output is not None,
                    repairs=max(adapter.complete_calls - 1, 0),
                    output=output,
                    error=error,
                )
                outputs.append(output_record)
                for score in _score_case(
                    spec=spec,
                    output_record=output_record,
                    gold=gold[case_id],
                    source=cases[case_id],
                ):
                    append_score(score_path, score)
                for record in adapter.case_records:
                    append_record(record, run_id)
            for score in score_version_selection(output_records=outputs, gold=gold):
                append_score(score_path, score)

    if not source_log.exists():
        raise SystemExit(f"No call records were written for {run_id}")
    run_docs_path.parent.mkdir(parents=True, exist_ok=True)
    run_docs_path.write_text(source_log.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"run_id={run_id}", flush=True)
    print(f"evaluations={planned_evaluations(tasks, model_names, limit)}", flush=True)
    print(f"wrote {run_docs_path} and {score_path}", flush=True)


def main(argv: Sequence[str] | None = None) -> None:
    settings = Settings.from_env()
    args = build_parser(settings).parse_args(argv)
    tasks: list[TaskName] = [args.task] if args.task else list(TASK_ORDER)
    model_names = [args.model] if args.model else list(settings.models)
    evaluate(
        run_id=args.run_id,
        tasks=tasks,
        model_names=model_names,
        settings=settings,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
