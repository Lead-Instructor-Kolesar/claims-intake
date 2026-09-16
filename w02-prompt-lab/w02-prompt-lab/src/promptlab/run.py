"""Day 5 evaluation harness: three tasks, two local models, deterministic scoring."""

from __future__ import annotations

import argparse
import json
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.corpus import GoldLabel, load_cases, validate_corpus
from promptlab.prompts import MissingPromptVariableError, load, render_user
from promptlab.records import OutputRecord, ScoreRecord, UsageRecord, append_record
from promptlab.report import write_reports
from promptlab.rules import VersionCandidate, select_current_version
from promptlab.schemas import (
    PolicyExtraction,
    StrictModel,
    SummarizationOutput,
    TaskName,
    TriageOutput,
    schema_description,
)
from promptlab.scoring import SCORER_VERSION, failure_scores, score_output
from promptlab.structured import complete_structured
from promptlab.usage import CallRecord

MAX_OUTPUT_TOKENS = 1536
TASK_SPECS: dict[TaskName, tuple[str, str, type[BaseModel]]] = {
    "summarization": ("summarize", "v1", SummarizationOutput),
    "extraction": ("extract", "v2", PolicyExtraction),
    "triage": ("triage", "v1", TriageOutput),
}


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local two-model prompt comparison")
    parser.add_argument("--run-id", help="Stable identifier for this run")
    parser.add_argument("--task", choices=["triage", "summarization", "extraction"])
    parser.add_argument("--model", choices=["mistral", "qwen"])
    parser.add_argument("--limit", type=int, help="Limit cases per task for a smoke run")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate configuration and corpus without calling Ollama",
    )
    return parser


def render_request_layers(
    task: TaskName, source: str
) -> tuple[str, str, str, str, type[BaseModel]]:
    prompt_id, version, schema = TASK_SPECS[task]
    template = load(prompt_id, version)
    description = schema_description(schema)
    system = template.system.replace("{schema_description}", description)
    variables: dict[str, str] = {}
    try:
        user = render_user(template, variables, source)
    except MissingPromptVariableError:
        variables["schema_description"] = description
        user = render_user(template, variables, source)
    return prompt_id, version, system, user, schema


def _kind_for_attempt(attempt: int, error_type: str | None) -> Literal[
    "primary", "transport_retry", "repair", "repair_retry"
]:
    if attempt <= 1:
        return "primary"
    if error_type in {"TransientProviderError"}:
        return "transport_retry"
    return "repair"


def _status_for_call(
    error_type: str | None,
) -> Literal["success", "schema_invalid", "transport_error"]:
    if error_type is None:
        return "success"
    if error_type in {"TransientProviderError"}:
        return "transport_error"
    return "schema_invalid"


def usage_from_calls(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model_name: str,
    model_id: str,
    prompt_version: str,
    calls: list[CallRecord],
    schema_failed: bool,
) -> list[UsageRecord]:
    records: list[UsageRecord] = []
    for index, call in enumerate(calls, start=1):
        status = _status_for_call(call.error_type)
        if schema_failed and call.error_type is None and index == len(calls):
            status = "schema_invalid"
        records.append(
            UsageRecord(
                run_id=run_id,
                task=task,
                case_id=case_id,
                model_name=model_name,
                model_id=model_id,
                prompt_version=prompt_version,
                attempt=call.attempt,
                kind=_kind_for_attempt(index, call.error_type),
                status=status,
                prompt_tokens=call.input_tokens,
                completion_tokens=call.output_tokens,
                latency_ms=float(call.latency_ms),
                cost_usd=Decimal(str(call.cost_usd)),
                error=call.error_type,
            )
        )
    return records


def load_call_records(run_id: str) -> list[CallRecord]:
    path = PROJECT_ROOT / "runs" / f"{run_id}.jsonl"
    if not path.exists():
        path = Path("runs") / f"{run_id}.jsonl"
    if not path.exists():
        return []
    records: list[CallRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(CallRecord.model_validate(json.loads(line)))
    return records


def _version_fields(output: StrictModel) -> tuple[str, str] | None:
    if isinstance(output, SummarizationOutput | PolicyExtraction):
        version = output.version
        effective = output.effective_date
        if (
            version.status == "present"
            and effective.status == "present"
            and isinstance(version.value, str)
            and isinstance(effective.value, str)
        ):
            return version.value, effective.value
    return None


def add_version_scores(
    *,
    run_id: str,
    task: TaskName,
    model_name: str,
    prompt_version: str,
    labels: list[GoldLabel],
    outputs: dict[str, StrictModel],
) -> list[ScoreRecord]:
    grouped: dict[str, list[GoldLabel]] = defaultdict(list)
    for label in labels:
        if label.version_group:
            grouped[label.version_group].append(label)
    records: list[ScoreRecord] = []
    for group_name, group_labels in grouped.items():
        if len(group_labels) < 2:
            continue
        expected = next(
            (
                label.expected_current_case_id
                for label in group_labels
                if label.expected_current_case_id
            ),
            None,
        )
        as_of_raw = next((label.as_of for label in group_labels if label.as_of), None)
        if expected is None or as_of_raw is None:
            continue
        candidates: list[VersionCandidate] = []
        for label in group_labels:
            output = outputs.get(label.id)
            if output is None:
                continue
            extracted = _version_fields(output)
            if extracted is None:
                continue
            version, effective_raw = extracted
            try:
                effective = date.fromisoformat(effective_raw)
            except ValueError:
                continue
            candidates.append(
                VersionCandidate(case_id=label.id, version=version, effective_date=effective)
            )
        selected = select_current_version(candidates, date.fromisoformat(as_of_raw))
        records.append(
            ScoreRecord(
                run_id=run_id,
                task=task,
                case_id=f"version:{group_name}",
                model_name=model_name,
                prompt_version=prompt_version,
                scorer_version=SCORER_VERSION,
                metric="version_selection_accuracy",
                numerator=int(selected is not None and selected.case_id == expected),
                denominator=1,
                detail=(
                    f"prompt_id={TASK_SPECS[task][0]} expected={expected} "
                    f"selected={selected.case_id if selected else 'none'}"
                ),
            )
        )
    return records


def main() -> None:
    args = _parser().parse_args()
    counts = validate_corpus()
    if args.validate_only:
        print("Corpus valid: " + ", ".join(f"{task}={count}" for task, count in counts.items()))
        return

    run_id = args.run_id or str(uuid.uuid4())
    limit = args.limit
    if limit is not None and limit < 1:
        raise SystemExit("--limit must be at least 1")

    selected_tasks: list[TaskName]
    if args.task:
        selected_tasks = [cast(TaskName, args.task)]
    else:
        selected_tasks = ["triage", "summarization", "extraction"]

    settings = Settings.from_env()
    selected_models = [args.model] if args.model else list(settings.models)

    docs_dir = PROJECT_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    outputs_path = docs_dir / "day5-run.jsonl"
    scores_path = docs_dir / "day5-scores.jsonl"
    for path in (outputs_path, scores_path):
        if path.exists():
            path.unlink()

    all_usage: list[UsageRecord] = []
    all_outputs: list[OutputRecord] = []
    all_scores: list[ScoreRecord] = []
    validated_by_task_model: dict[tuple[TaskName, str], dict[str, StrictModel]] = defaultdict(dict)
    labels_by_task: dict[TaskName, list[GoldLabel]] = defaultdict(list)
    adapters: dict[str, OllamaAdapter] = {
        name: OllamaAdapter(
            model_id=settings.models[name].model_id,
            base_url=settings.ollama_base_url,
        )
        for name in selected_models
    }

    for task in selected_tasks:
        pairs = load_cases(task)
        if limit is not None:
            pairs = pairs[:limit]
        labels_by_task[task] = [gold for _case, gold in pairs]
        prompt_id, prompt_version, schema = TASK_SPECS[task]
        for model_name in selected_models:
            model = settings.models[model_name]
            adapter = adapters[model_name]
            for case, gold in pairs:
                _pid, _ver, system, user, _schema = render_request_layers(task, case.source)
                request = CompletionRequest(
                    task=task,
                    case_id=case.id,
                    prompt_id=prompt_id,
                    prompt_version=prompt_version,
                    system=system,
                    user_content=user,
                    temperature=0.0,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                )
                counter = CountingAdapter(adapter)
                parsed: BaseModel | None = None
                error: str | None = None
                try:
                    parsed = complete_structured(
                        counter,
                        request,
                        schema,
                        run_id,
                        max_repairs=settings.max_schema_repairs,
                    )
                except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                    error = str(exc)
                output_record = OutputRecord(
                    run_id=run_id,
                    task=task,
                    case_id=case.id,
                    model_name=model_name,
                    model_id=model.model_id,
                    prompt_version=prompt_version,
                    succeeded=parsed is not None,
                    repairs=max(0, counter.calls - 1),
                    output=parsed.model_dump() if parsed is not None else None,
                    error=error,
                )
                if parsed is not None and isinstance(parsed, StrictModel):
                    validated_by_task_model[(task, model_name)][case.id] = parsed
                case_scores = (
                    score_output(
                        run_id=run_id,
                        task=task,
                        case_id=case.id,
                        model_name=model_name,
                        prompt_version=prompt_version,
                        output=parsed,
                        gold=gold,
                        source=case.source,
                    )
                    if parsed is not None
                    else failure_scores(
                        run_id=run_id,
                        task=task,
                        case_id=case.id,
                        model_name=model_name,
                        prompt_version=prompt_version,
                        gold=gold,
                    )
                )
                join = f"prompt_id={prompt_id} model_id={model.model_id}"
                for score in case_scores:
                    extra = f"{join} {score.detail}" if score.detail else join
                    score.detail = extra
                append_record(outputs_path, output_record)
                all_outputs.append(output_record)
                for score in case_scores:
                    append_record(scores_path, score)
                    all_scores.append(score)
                status = "ok" if output_record.succeeded else "failed"
                print(
                    f"{task:13} {model_name:8} {case.id:5} "
                    f"{status} repairs={output_record.repairs}",
                    flush=True,
                )

    for task in selected_tasks:
        if task == "triage":
            continue
        _prompt_id, prompt_version, _schema = TASK_SPECS[task]
        for model_name in selected_models:
            version_scores = add_version_scores(
                run_id=run_id,
                task=task,
                model_name=model_name,
                prompt_version=prompt_version,
                labels=labels_by_task[task],
                outputs=validated_by_task_model[(task, model_name)],
            )
            for record in version_scores:
                append_record(scores_path, record)
                all_scores.append(record)

    calls = load_call_records(run_id)
    calls_by_key: dict[tuple[str, str, str, str], list[CallRecord]] = defaultdict(list)
    for call in calls:
        calls_by_key[(call.task, call.case_id, call.prompt_version, call.model_id)].append(call)
    for output_record in all_outputs:
        key = (
            output_record.task,
            output_record.case_id,
            output_record.prompt_version,
            output_record.model_id,
        )
        all_usage.extend(
            usage_from_calls(
                run_id=run_id,
                task=output_record.task,
                case_id=output_record.case_id,
                model_name=output_record.model_name,
                model_id=output_record.model_id,
                prompt_version=output_record.prompt_version,
                calls=calls_by_key.get(key, []),
                schema_failed=not output_record.succeeded,
            )
        )

    write_reports(
        run_id=run_id,
        models=selected_models,
        usage=all_usage,
        outputs=all_outputs,
        scores=all_scores,
        report_path=PROJECT_ROOT / "reports" / "comparison.md",
        decision_path=PROJECT_ROOT / "docs" / "model-decision.md",
    )
    print(f"run_id={run_id}")
    print(f"Report: {PROJECT_ROOT / 'reports' / 'comparison.md'}")
    print("Recorded provider cost: $0.00")


if __name__ == "__main__":
    main()
