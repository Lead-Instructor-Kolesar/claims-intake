"""Day 5 evaluation harness: 3 tasks x 2 models x corpus cases."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import MAX_OUTPUT_TOKENS, PROJECT_ROOT, TASK_PROMPTS, ModelConfig, Settings
from promptlab.corpus import GoldLabel, load_cases, validate_corpus
from promptlab.prompts import load, render_user
from promptlab.records import (
    OutputRecord,
    ScoreRecord,
    UsageRecord,
)
from promptlab.records import (
    append_record as append_lab_record,
)
from promptlab.report import write_reports
from promptlab.rules import VersionCandidate
from promptlab.schemas import (
    OUTPUT_SCHEMAS,
    PolicyExtraction,
    StrictModel,
    SummarizationOutput,
    TaskName,
    schema_description,
)
from promptlab.scoring import failure_scores, score_output, score_version_selection
from promptlab.structured import complete_structured
from promptlab.usage import CallRecord
from promptlab.usage import append_record as append_call_record

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
DOCS_RUN_PATH = PROJECT_ROOT / "docs" / "day5-run.jsonl"
DOCS_SCORES_PATH = PROJECT_ROOT / "docs" / "day5-scores.jsonl"
REPORT_PATH = PROJECT_ROOT / "reports" / "comparison.md"
DECISION_PATH = PROJECT_ROOT / "docs" / "model-decision.md"

AdapterFactory = Callable[[ModelConfig, Settings], ModelAdapter]


class RecordingAdapter:
    """Wrap an adapter and retain every CallRecord from semantic completions."""

    def __init__(self, inner: ModelAdapter) -> None:
        self._inner = inner
        self.provider = inner.provider
        self.model_id = inner.model_id
        self.calls = 0
        self.records: list[CallRecord] = []
        self._semantic_batches: list[list[CallRecord]] = []

    def reset(self) -> None:
        self.calls = 0
        self.records = []
        self._semantic_batches = []

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        self.calls += 1
        result = self._inner.complete(request, run_id)
        self.records.extend(result.records)
        self._semantic_batches.append(list(result.records))
        return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local two-model prompt comparison (Day 5)"
    )
    parser.add_argument("--run-id", help="Stable identifier for this run")
    parser.add_argument(
        "--task",
        choices=["triage", "summarization", "extraction"],
        help="Optional task filter; default runs all three",
    )
    parser.add_argument(
        "--model",
        choices=["mistral", "qwen"],
        help="Optional model filter; default runs both configured models",
    )
    parser.add_argument("--limit", type=int, help="Limit cases per task for a smoke run")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate configuration and corpus without calling Ollama",
    )
    return parser


def _default_adapter_factory(model: ModelConfig, settings: Settings) -> ModelAdapter:
    return OllamaAdapter(model_id=model.model_id, base_url=settings.ollama_base_url)


def _usage_kind(semantic_call: int, attempt: int) -> str:
    if semantic_call == 1 and attempt == 1:
        return "primary"
    if semantic_call == 1 and attempt > 1:
        return "transport_retry"
    if semantic_call > 1 and attempt == 1:
        return "repair"
    return "repair_retry"


def _classify_usage(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model: ModelConfig,
    prompt_version: str,
    batches: list[list[CallRecord]],
    succeeded: bool,
) -> list[UsageRecord]:
    records: list[UsageRecord] = []
    flat = [record for batch in batches for record in batch]
    final_id = flat[-1].record_id if flat and succeeded else None

    for semantic_index, batch in enumerate(batches, start=1):
        for call in batch:
            if call.error_type is not None:
                status = "transport_error"
            elif final_id is not None and call.record_id == final_id:
                status = "success"
            else:
                status = "schema_invalid"
            records.append(
                UsageRecord(
                    run_id=run_id,
                    task=task,
                    case_id=case_id,
                    model_name=model.logical_name,
                    model_id=model.model_id,
                    prompt_version=prompt_version,
                    attempt=call.attempt,
                    kind=_usage_kind(semantic_index, call.attempt),  # type: ignore[arg-type]
                    status=status,  # type: ignore[arg-type]
                    prompt_tokens=call.input_tokens,
                    completion_tokens=call.output_tokens,
                    latency_ms=float(call.latency_ms),
                    cost_usd=Decimal(str(call.cost_usd)),
                    error=call.error_type,
                )
            )
    return records


def _render_prompt(
    task: TaskName,
    source: str,
) -> tuple[str, str, str, str]:
    prompt_id, prompt_version = TASK_PROMPTS[task]
    schema = OUTPUT_SCHEMAS[task]
    template = load(prompt_id, prompt_version)
    schema_text = schema_description(schema)
    system = template.system.replace("{schema_description}", schema_text)
    user_content = render_user(
        template,
        variables={"schema_description": schema_text},
        untrusted=source,
    )
    return system, user_content, prompt_id, prompt_version


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


def _add_version_scores(
    *,
    run_id: str,
    task: TaskName,
    model_name: str,
    prompt_version: str,
    labels: list[GoldLabel],
    outputs: dict[str, StrictModel],
    scores_path: Path,
    all_scores: list[ScoreRecord],
) -> None:
    grouped: dict[str, list[GoldLabel]] = defaultdict(list)
    for label in labels:
        if label.version_group:
            grouped[label.version_group].append(label)

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
                VersionCandidate(
                    case_id=label.id, version=version, effective_date=effective
                )
            )

        record = score_version_selection(
            run_id=run_id,
            task=task,
            model_name=model_name,
            prompt_version=prompt_version,
            group_name=group_name,
            expected_case_id=expected,
            as_of=date.fromisoformat(as_of_raw),
            candidates=candidates,
        )
        append_lab_record(scores_path, record)
        all_scores.append(record)


def run_evaluation(
    *,
    run_id: str,
    tasks: list[TaskName],
    model_names: list[str],
    limit: int | None,
    settings: Settings,
    adapter_factory: AdapterFactory | None = None,
    docs_run_path: Path = DOCS_RUN_PATH,
    docs_scores_path: Path = DOCS_SCORES_PATH,
    report_path: Path = REPORT_PATH,
    decision_path: Path = DECISION_PATH,
    runs_root: Path | None = None,
) -> tuple[list[UsageRecord], list[OutputRecord], list[ScoreRecord]]:
    factory = adapter_factory or _default_adapter_factory
    root = runs_root if runs_root is not None else PROJECT_ROOT / "runs"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    usage_path = run_dir / "usage.jsonl"
    outputs_path = run_dir / "outputs.jsonl"
    scores_path = run_dir / "scores.jsonl"

    all_usage: list[UsageRecord] = []
    all_outputs: list[OutputRecord] = []
    all_scores: list[ScoreRecord] = []
    validated: dict[tuple[TaskName, str], dict[str, StrictModel]] = defaultdict(dict)
    labels_by_task: dict[TaskName, list[GoldLabel]] = {}
    prompt_versions: dict[TaskName, str] = {}

    for task in tasks:
        pairs = load_cases(task)
        if limit is not None:
            pairs = pairs[:limit]
        labels_by_task[task] = [gold for _case, gold in pairs]
        schema = OUTPUT_SCHEMAS[task]

        for model_name in model_names:
            model = settings.models[model_name]
            adapter = RecordingAdapter(factory(model, settings))

            for case, gold in pairs:
                system, user_content, prompt_id, prompt_version = _render_prompt(
                    task, case.document_text
                )
                prompt_versions[task] = prompt_version
                request = CompletionRequest(
                    task=task,
                    case_id=case.id,
                    prompt_id=prompt_id,
                    prompt_version=prompt_version,
                    system=system,
                    user_content=user_content,
                    temperature=0.0,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                )
                adapter.reset()
                parsed: StrictModel | None = None
                error: str | None = None
                try:
                    parsed = complete_structured(
                        adapter,
                        request,
                        schema,
                        run_id,
                        max_repairs=settings.max_schema_repairs,
                    )
                    succeeded = True
                except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                    succeeded = False
                    error = str(exc)

                for call in adapter.records:
                    append_call_record(call, run_id)

                usage_rows = _classify_usage(
                    run_id=run_id,
                    task=task,
                    case_id=case.id,
                    model=model,
                    prompt_version=prompt_version,
                    batches=adapter._semantic_batches,
                    succeeded=succeeded,
                )
                for usage in usage_rows:
                    append_lab_record(usage_path, usage)
                    all_usage.append(usage)

                output_record = OutputRecord(
                    run_id=run_id,
                    task=task,
                    case_id=case.id,
                    model_name=model_name,
                    model_id=model.model_id,
                    prompt_version=prompt_version,
                    succeeded=succeeded,
                    repairs=max(0, adapter.calls - 1),
                    output=None if parsed is None else parsed.model_dump(mode="json"),
                    error=error,
                )
                append_lab_record(outputs_path, output_record)
                all_outputs.append(output_record)

                if parsed is not None:
                    validated[(task, model_name)][case.id] = parsed
                    case_scores = score_output(
                        run_id=run_id,
                        task=task,
                        case_id=case.id,
                        model_name=model_name,
                        prompt_version=prompt_version,
                        output=parsed,
                        gold=gold,
                        source=case.document_text,
                    )
                else:
                    case_scores = failure_scores(
                        run_id=run_id,
                        task=task,
                        case_id=case.id,
                        model_name=model_name,
                        prompt_version=prompt_version,
                        gold=gold,
                    )
                for score in case_scores:
                    append_lab_record(scores_path, score)
                    all_scores.append(score)

                print(
                    f"{task:13} {model_name:8} {case.id:5} "
                    f"{'ok' if succeeded else 'failed'}",
                    flush=True,
                )

            if task != "triage":
                _add_version_scores(
                    run_id=run_id,
                    task=task,
                    model_name=model_name,
                    prompt_version=prompt_versions.get(task, TASK_PROMPTS[task][1]),
                    labels=labels_by_task[task],
                    outputs=validated[(task, model_name)],
                    scores_path=scores_path,
                    all_scores=all_scores,
                )

    _write_day5_docs(
        usage=all_usage,
        outputs=all_outputs,
        scores=all_scores,
        docs_run_path=docs_run_path,
        docs_scores_path=docs_scores_path,
    )
    write_reports(
        run_id=run_id,
        models=model_names,
        usage=all_usage,
        outputs=all_outputs,
        scores=all_scores,
        report_path=report_path,
        decision_path=decision_path,
    )
    return all_usage, all_outputs, all_scores


def _write_day5_docs(
    *,
    usage: list[UsageRecord],
    outputs: list[OutputRecord],
    scores: list[ScoreRecord],
    docs_run_path: Path,
    docs_scores_path: Path,
) -> None:
    docs_run_path.parent.mkdir(parents=True, exist_ok=True)
    grouped: dict[tuple[str, str, str], list[UsageRecord]] = defaultdict(list)
    for row in usage:
        grouped[(row.task, row.model_name, row.case_id)].append(row)

    lines: list[str] = []
    for output in outputs:
        key = (output.task, output.model_name, output.case_id)
        for usage_row in grouped.get(key, []):
            lines.append(usage_row.model_dump_json())
        lines.append(output.model_dump_json())
    docs_run_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    docs_scores_path.write_text(
        "".join(score.model_dump_json() + "\n" for score in scores),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    counts = validate_corpus()
    if args.validate_only:
        print(
            "Corpus valid: "
            + ", ".join(f"{task}={count}" for task, count in counts.items())
        )
        return

    run_id = cast(str | None, args.run_id)
    if run_id is None or not RUN_ID_PATTERN.fullmatch(run_id):
        raise SystemExit(
            "--run-id is required and must use letters, numbers, '.', '_' or '-'"
        )
    limit = cast(int | None, args.limit)
    if limit is not None and limit < 1:
        raise SystemExit("--limit must be at least 1")

    selected_tasks: list[TaskName]
    if args.task:
        selected_tasks = [cast(TaskName, args.task)]
    else:
        selected_tasks = ["triage", "summarization", "extraction"]

    settings = Settings.from_env()
    selected_models = [cast(str, args.model)] if args.model else list(settings.models)

    run_evaluation(
        run_id=run_id,
        tasks=selected_tasks,
        model_names=selected_models,
        limit=limit,
        settings=settings,
    )
    print(f"Report: {REPORT_PATH}")
    print(f"Decision: {DECISION_PATH}")


if __name__ == "__main__":
    main()
