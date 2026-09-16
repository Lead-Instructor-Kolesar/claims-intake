from __future__ import annotations

import argparse
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

from promptlab.config import PROJECT_ROOT, ModelConfig, Settings
from promptlab.corpus import GoldLabel, load_cases, validate_corpus
from promptlab.prompts import build_prompt, prompt_version
from promptlab.providers import CompletionFailed, OllamaProvider
from promptlab.records import OutputRecord, ScoreRecord, UsageRecord, append_record
from promptlab.report import write_reports
from promptlab.rules import VersionCandidate, select_current_version
from promptlab.schemas import (
    OUTPUT_SCHEMAS,
    PolicyExtraction,
    StrictModel,
    SummarizationOutput,
    TaskName,
)
from promptlab.scoring import SCORER_VERSION, failure_scores, score_output

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


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


def _usage_record(
    *,
    run_id: str,
    task: TaskName,
    case_id: str,
    model: ModelConfig,
    version: str,
    attempt: object,
) -> UsageRecord:
    from promptlab.providers import AttemptData

    data = cast(AttemptData, attempt)
    return UsageRecord(
        run_id=run_id,
        task=task,
        case_id=case_id,
        model_name=model.logical_name,
        model_id=model.model_id,
        prompt_version=version,
        attempt=data.attempt,
        kind=data.kind,
        status=data.status,
        prompt_tokens=data.prompt_tokens,
        completion_tokens=data.completion_tokens,
        latency_ms=data.latency_ms,
        cost_usd=data.cost_usd,
        error=data.error,
    )


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
        prompt_versions: set[str] = set()
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
            prompt_versions.add(prompt_version(task, model_name))
        selected = select_current_version(candidates, date.fromisoformat(as_of_raw))
        record = ScoreRecord(
            run_id=run_id,
            task=task,
            case_id=f"version:{group_name}",
            model_name=model_name,
            prompt_version=",".join(sorted(prompt_versions)) or prompt_version(task, model_name),
            scorer_version=SCORER_VERSION,
            metric="version_selection_accuracy",
            numerator=int(selected is not None and selected.case_id == expected),
            denominator=1,
            detail=f"expected={expected}; selected={selected.case_id if selected else 'none'}",
        )
        append_record(scores_path, record)
        all_scores.append(record)


def main() -> None:
    args = _parser().parse_args()
    counts = validate_corpus()
    if args.validate_only:
        print("Corpus valid: " + ", ".join(f"{task}={count}" for task, count in counts.items()))
        return

    run_id = cast(str | None, args.run_id)
    if run_id is None or not RUN_ID_PATTERN.fullmatch(run_id):
        raise SystemExit("--run-id is required and must use letters, numbers, '.', '_' or '-'")
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
    run_dir = PROJECT_ROOT / "runs" / run_id
    if run_dir.exists():
        raise SystemExit(f"Run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    usage_path = run_dir / "usage.jsonl"
    outputs_path = run_dir / "outputs.jsonl"
    scores_path = run_dir / "scores.jsonl"

    all_usage: list[UsageRecord] = []
    all_outputs: list[OutputRecord] = []
    all_scores: list[ScoreRecord] = []
    total_cost = Decimal("0")
    validated_by_task_model: dict[tuple[TaskName, str], dict[str, StrictModel]] = defaultdict(dict)
    labels_by_task: dict[TaskName, list[GoldLabel]] = defaultdict(list)

    provider = OllamaProvider(settings)
    try:
        for task in selected_tasks:
            pairs = load_cases(task)
            if limit is not None:
                pairs = pairs[:limit]
            labels_by_task[task] = [gold for _case, gold in pairs]
            for model_name in selected_models:
                model = settings.models[model_name]
                version = prompt_version(task, model_name)
                for case, gold in pairs:
                    if total_cost >= settings.per_run_cap_usd:
                        raise SystemExit(
                            f"Per-run cost cap reached before {task}/{model_name}/{case.id}"
                        )
                    prompt = build_prompt(task, model_name, case.source)
                    try:
                        result = provider.complete(
                            model=model,
                            prompt=prompt,
                            output_schema=OUTPUT_SCHEMAS[task],
                        )
                        for attempt in result.attempts:
                            usage_record = _usage_record(
                                run_id=run_id,
                                task=task,
                                case_id=case.id,
                                model=model,
                                version=version,
                                attempt=attempt,
                            )
                            append_record(usage_path, usage_record)
                            all_usage.append(usage_record)
                            total_cost += usage_record.cost_usd
                        output_record = OutputRecord(
                            run_id=run_id,
                            task=task,
                            case_id=case.id,
                            model_name=model_name,
                            model_id=model.model_id,
                            prompt_version=version,
                            succeeded=True,
                            repairs=result.repairs,
                            output=result.output.model_dump(mode="json"),
                        )
                        validated_by_task_model[(task, model_name)][case.id] = result.output
                        case_scores = score_output(
                            run_id=run_id,
                            task=task,
                            case_id=case.id,
                            model_name=model_name,
                            prompt_version=version,
                            output=result.output,
                            gold=gold,
                            source=case.source,
                        )
                    except CompletionFailed as exc:
                        for attempt in exc.attempts:
                            usage_record = _usage_record(
                                run_id=run_id,
                                task=task,
                                case_id=case.id,
                                model=model,
                                version=version,
                                attempt=attempt,
                            )
                            append_record(usage_path, usage_record)
                            all_usage.append(usage_record)
                            total_cost += usage_record.cost_usd
                        output_record = OutputRecord(
                            run_id=run_id,
                            task=task,
                            case_id=case.id,
                            model_name=model_name,
                            model_id=model.model_id,
                            prompt_version=version,
                            succeeded=False,
                            repairs=exc.repairs,
                            output=None,
                            error=str(exc),
                        )
                        case_scores = failure_scores(
                            run_id=run_id,
                            task=task,
                            case_id=case.id,
                            model_name=model_name,
                            prompt_version=version,
                            gold=gold,
                        )
                    append_record(outputs_path, output_record)
                    all_outputs.append(output_record)
                    for score in case_scores:
                        append_record(scores_path, score)
                        all_scores.append(score)
                    print(
                        f"{task:13} {model_name:8} {case.id:5} "
                        f"{'ok' if output_record.succeeded else 'failed'}"
                    )
    finally:
        provider.close()

    for task in selected_tasks:
        if task == "triage":
            continue
        for model_name in selected_models:
            _add_version_scores(
                run_id=run_id,
                task=task,
                model_name=model_name,
                labels=labels_by_task[task],
                outputs=validated_by_task_model[(task, model_name)],
                scores_path=scores_path,
                all_scores=all_scores,
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
    print(f"Report: {PROJECT_ROOT / 'reports' / 'comparison.md'}")
    print(f"Recorded provider cost: ${total_cost}")


if __name__ == "__main__":
    main()
