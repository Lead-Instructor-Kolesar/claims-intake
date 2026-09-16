"""Reporting for the Week 2 model-comparison lab.

The reporting layer consumes the existing UsageRecord, OutputRecord, and
ScoreRecord objects.  It does not rescore model output and it does not call an
LLM.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from promptlab.config import MAX_OUTPUT_TOKENS, PROMPT_HOME_MODEL, TASK_PROMPTS
from promptlab.records import OutputRecord, ScoreRecord, UsageRecord

_ConfigKey = tuple[str, str, str]  # task, model_name, prompt_version


@dataclass(frozen=True)
class _ConfigStats:
    key: _ConfigKey
    metrics: dict[str, tuple[int, int, bool | None]]
    input_tokens_per_case: float | None
    output_tokens_per_case: float | None
    median_latency_ms: float | None
    max_latency_ms: float | None
    observations: int
    repairs: int
    retries: int
    failures: int
    cases: int
    disqualified: bool


def _key(record: Any) -> _ConfigKey:
    return (
        str(record.task),
        str(record.model_name),
        str(record.prompt_version),
    )


def _for_run(records: Sequence[Any], run_id: str) -> list[Any]:
    return [record for record in records if str(record.run_id) == run_id]


def _fmt_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _prompt_label(task: str, model_name: str, prompt_version: str) -> str:
    configured = TASK_PROMPTS.get(task)  # type: ignore[call-overload]
    if configured is None:
        prompt_id, version = task, prompt_version
    else:
        prompt_id, default_version = configured
        version = prompt_version or default_version
    label = f"{prompt_id}.{version}"
    if model_name != PROMPT_HOME_MODEL:
        return f"{label} (transfer)"
    return label


def _aggregate_scores(
    records: Sequence[ScoreRecord],
) -> dict[str, tuple[int, int, bool | None]]:
    """Aggregate compatible score counts without averaging percentages."""

    grouped: dict[str, list[ScoreRecord]] = defaultdict(list)
    for record in records:
        grouped[str(record.metric)].append(record)

    result: dict[str, tuple[int, int, bool | None]] = {}

    for metric, rows in sorted(grouped.items()):
        numerator = sum(int(row.numerator) for row in rows)
        denominator = sum(int(row.denominator) for row in rows)

        directions = {
            bool(value)
            for value in (getattr(row, "lower_is_better", None) for row in rows)
            if value is not None
        }
        lower_is_better: bool | None = (
            next(iter(directions)) if len(directions) == 1 else None
        )

        result[metric] = (numerator, denominator, lower_is_better)

    return result


def _metric_text(metrics: dict[str, tuple[int, int, bool | None]]) -> str:
    if not metrics:
        return "—"

    rendered: list[str] = []
    for metric, (numerator, denominator, lower_is_better) in metrics.items():
        suffix = " ↓" if lower_is_better else ""
        rendered.append(f"{metric}: {numerator}/{denominator}{suffix}")

    return "<br>".join(rendered)


def _config_stats(
    *,
    key: _ConfigKey,
    usage: Sequence[UsageRecord],
    outputs: Sequence[OutputRecord],
    scores: Sequence[ScoreRecord],
) -> _ConfigStats:
    metrics = _aggregate_scores(scores)
    cases = len({row.case_id for row in outputs}) or len({row.case_id for row in usage})
    prompt_tokens = sum(int(row.prompt_tokens) for row in usage)
    completion_tokens = sum(int(row.completion_tokens) for row in usage)
    latencies = [float(row.latency_ms) for row in usage]
    retries = sum(
        1
        for row in usage
        if int(row.attempt) > 1 and str(row.kind) in {"transport_retry", "repair_retry"}
    )
    repairs = sum(1 for row in outputs if int(row.repairs) > 0)
    failures = sum(1 for row in outputs if not row.succeeded)

    boundary = metrics.get("human_boundary_compliance")
    pii = metrics.get("pii_leakage")
    disqualified = False
    if boundary is not None and boundary[1] > 0 and boundary[0] < boundary[1]:
        disqualified = True
    if pii is not None and pii[0] > 0:
        disqualified = True

    return _ConfigStats(
        key=key,
        metrics=metrics,
        input_tokens_per_case=(prompt_tokens / cases) if cases else None,
        output_tokens_per_case=(completion_tokens / cases) if cases else None,
        median_latency_ms=float(median(latencies)) if latencies else None,
        max_latency_ms=float(max(latencies)) if latencies else None,
        observations=len(latencies),
        repairs=repairs,
        retries=retries,
        failures=failures,
        cases=cases,
        disqualified=disqualified,
    )


def _all_config_keys(
    usage: Sequence[UsageRecord],
    outputs: Sequence[OutputRecord],
    scores: Sequence[ScoreRecord],
) -> list[_ConfigKey]:
    keys = {_key(row) for row in usage}
    keys.update(_key(row) for row in outputs)
    keys.update(_key(row) for row in scores)
    return sorted(keys)


def _ratio(metrics: dict[str, tuple[int, int, bool | None]], name: str) -> float:
    numerator, denominator, _direction = metrics.get(name, (0, 0, None))
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _select_config(task: str, configs: Sequence[_ConfigStats]) -> _ConfigStats | None:
    eligible = [config for config in configs if not config.disqualified]
    if not eligible:
        return None

    def sort_key(config: _ConfigStats) -> tuple[float, ...]:
        metrics = config.metrics
        latency = config.median_latency_ms if config.median_latency_ms is not None else 1e18
        out_tokens = (
            config.output_tokens_per_case
            if config.output_tokens_per_case is not None
            else 1e18
        )
        if task == "triage":
            return (
                -_ratio(metrics, "queue_accuracy"),
                -_ratio(metrics, "escalation_accuracy"),
                _ratio(metrics, "missed_escalation"),
                latency,
                out_tokens,
            )
        return (
            -_ratio(metrics, "required_evidence_recall"),
            -_ratio(metrics, "citation_correctness"),
            -_ratio(metrics, "unsupported_field_avoidance"),
            latency,
            out_tokens,
        )

    return sorted(eligible, key=sort_key)[0]


def _failure_clause(stats: _ConfigStats) -> str:
    if stats.failures == 1:
        return "; 1 generation failure scored as zeros"
    if stats.failures > 1:
        return f"; {stats.failures} generation failures scored as zeros"
    return "; no generation failures"


def _selection_reason(task: str, winner: _ConfigStats) -> str:
    metrics = winner.metrics
    if task == "triage":
        queue = metrics.get("queue_accuracy", (0, 0, None))
        escalation = metrics.get("escalation_accuracy", (0, 0, None))
        missed = metrics.get("missed_escalation", (0, 0, None))
        return (
            f"highest queue_accuracy ({queue[0]}/{queue[1]}), then escalation_accuracy "
            f"({escalation[0]}/{escalation[1]}), then fewer missed escalations "
            f"({missed[0]}/{missed[1]})"
            f"{_failure_clause(winner)}"
        )
    recall = metrics.get("required_evidence_recall", (0, 0, None))
    citation = metrics.get("citation_correctness", (0, 0, None))
    avoidance = metrics.get("unsupported_field_avoidance", (0, 0, None))
    return (
        f"highest required_evidence_recall ({recall[0]}/{recall[1]}), then "
        f"citation_correctness ({citation[0]}/{citation[1]}), then "
        f"unsupported_field_avoidance ({avoidance[0]}/{avoidance[1]})"
        f"{_failure_clause(winner)}"
    )


def _write_report(
    *,
    run_id: str,
    usage: Sequence[UsageRecord],
    outputs: Sequence[OutputRecord],
    scores: Sequence[ScoreRecord],
    report_path: Path,
    decisions: dict[str, _ConfigStats | None],
) -> None:
    lines: list[str] = [
        "# Model Comparison",
        "",
        f"Run ID: `{run_id}`",
        "",
        "Counts are reported with their denominators. "
        "Latency uses median and maximum rather than mean. "
        "Local Ollama provider/API charge is `$0.00`.",
        "",
    ]

    keys = _all_config_keys(usage, outputs, scores)
    tasks = sorted({task for task, _model, _prompt in keys})
    stats_by_task: dict[str, list[_ConfigStats]] = defaultdict(list)

    if not tasks:
        lines.extend(["No records were supplied for this run.", ""])

    for task in tasks:
        lines.extend(
            [
                f"## {task.title()}",
                "",
                "| Model | Prompt | Quality | Input tokens/case | Output tokens/case | "
                "Median latency | Max latency | n | Repairs | Retries | Failures |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )

        task_keys = [key for key in keys if key[0] == task]
        for key in task_keys:
            _task, model_name, prompt_version = key
            u = [row for row in usage if _key(row) == key]
            o = [row for row in outputs if _key(row) == key]
            s = [row for row in scores if _key(row) == key]
            stats = _config_stats(key=key, usage=u, outputs=o, scores=s)
            stats_by_task[task].append(stats)

            input_tokens = (
                _fmt_number(stats.input_tokens_per_case)
                if stats.input_tokens_per_case is not None
                else "—"
            )
            output_tokens = (
                _fmt_number(stats.output_tokens_per_case)
                if stats.output_tokens_per_case is not None
                else "—"
            )
            median_latency = (
                f"{_fmt_number(stats.median_latency_ms)} ms"
                if stats.median_latency_ms is not None
                else "—"
            )
            max_latency = (
                f"{_fmt_number(stats.max_latency_ms)} ms"
                if stats.max_latency_ms is not None
                else "—"
            )
            prompt = _prompt_label(task, model_name, prompt_version)
            lines.append(
                "| "
                f"{model_name} | {prompt} | {_metric_text(stats.metrics)} | "
                f"{input_tokens} | {output_tokens} | {median_latency} | {max_latency} | "
                f"{stats.observations} | {stats.repairs} | {stats.retries} | "
                f"{stats.failures} |"
            )

        lines.append("")

    lines.extend(
        [
            "## Recommendation",
            "",
        ]
    )
    if decisions:
        for task in sorted(decisions):
            winner = decisions[task]
            if winner is None:
                lines.append(
                    f"- `{task}`: no eligible configuration "
                    "(human-boundary or PII failure disqualified all candidates)."
                )
                continue
            _task, model_name, prompt_version = winner.key
            label = _prompt_label(task, model_name, prompt_version)
            lines.append(
                f"- `{task}`: **{model_name}** with `{label}` "
                f"because {_selection_reason(task, winner)}. "
                "Reopen if a newer prompt version or model changes measured quality, "
                "latency, or boundary/PII outcomes on this corpus."
            )
    else:
        lines.append("- No configurations supplied.")
    lines.append("")

    evaluated_models = sorted({model for _task, model, _prompt in keys})
    model_clause = (
        f" (`{'`, `'.join(evaluated_models)}`)." if evaluated_models else "."
    )
    model_count_phrase = (
        "both evaluated models" if len(evaluated_models) >= 2 else "the evaluated model"
    )
    failed = sum(stat.failures for rows in stats_by_task.values() for stat in rows)
    limits = [
        "## Human boundary",
        "",
        f"Draft replies were checked for customer-outcome language under {model_count_phrase}"
        f"{model_clause}",
        "A configuration with any human-boundary failure or PII leak is disqualified "
        "from selection.",
        "",
        "## Limits",
        "",
        "- Each task uses a fixed 12-case sample; treat counts as lab evidence, not "
        "production-scale precision.",
        "- Transfer rows reuse prompts developed on the home model; they are not proof "
        "of the best adapted prompt for the transferred model.",
        "- Untested combinations (other prompt versions, temperatures, or models) are "
        "out of scope for this run.",
        "- Latency and throughput depend on local hardware and Ollama runtime state.",
        f"- Both models used a shared max_output_tokens of {MAX_OUTPUT_TOKENS}.",
    ]
    if failed == 1:
        limits.append(
            "- 1 evaluation produced no validated output (including truncated "
            "generations) and was scored as zeros; that row affects recall ranking."
        )
    elif failed:
        limits.append(
            f"- {failed} evaluations produced no validated output (including truncated "
            "generations) and were scored as zeros; those rows affect recall ranking."
        )
    limits.extend(
        [
            "- This report does not claim production readiness or invent a dollar cost "
            "comparison; local provider charge remains `$0.00`.",
            "",
        ]
    )
    lines.extend(limits)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _write_decision(
    *,
    run_id: str,
    models: Sequence[str],
    usage: Sequence[UsageRecord],
    outputs: Sequence[OutputRecord],
    scores: Sequence[ScoreRecord],
    decision_path: Path,
    decisions: dict[str, _ConfigStats | None],
    stats_by_task: dict[str, list[_ConfigStats]],
) -> None:
    keys = _all_config_keys(usage, outputs, scores)
    lines: list[str] = [
        "# Model Decision Record",
        "",
        f"Run ID: `{run_id}`",
        "",
        "Selection follows the committed Day 5 rule: triage prefers queue_accuracy, then "
        "escalation_accuracy, then fewer missed escalations, and disqualifies human-boundary "
        "or PII failures; summarization/extraction prefer required_evidence_recall, then "
        "citation_correctness, then unsupported_field_avoidance; ties break on median "
        "latency, then output tokens per case.",
        "",
        "## Evaluated models",
        "",
    ]

    evaluated_models = sorted(
        {model for _task, model, _prompt in keys} | {str(model) for model in models}
    )
    if evaluated_models:
        for model in evaluated_models:
            lines.append(f"- {model}")
    else:
        lines.append("- None")

    lines.extend(["", "## Evidence rows", ""])
    if keys:
        for task, model, prompt in keys:
            lines.append(
                f"- `{task}` / {model} / `{_prompt_label(task, model, prompt)}`"
            )
    else:
        lines.append("- No configurations supplied.")

    lines.extend(["", "## Task decisions", ""])
    for task in sorted(set(stats_by_task) | set(decisions)):
        winner = decisions.get(task)
        configs = stats_by_task.get(task, [])
        lines.append(f"### {task}")
        lines.append("")
        if winner is None:
            lines.append("- selected model: none (all candidates disqualified)")
            lines.append("- prompt version: n/a")
            lines.append("- measured reason: human-boundary or PII failure")
        else:
            _task, model_name, prompt_version = winner.key
            lines.append(f"- selected model: {model_name}")
            lines.append(f"- prompt version: `{_prompt_label(task, model_name, prompt_version)}`")
            lines.append(f"- measured reason: {_selection_reason(task, winner)}")
        rejected = [
            config
            for config in configs
            if winner is None or config.key != winner.key
        ]
        if rejected:
            bits: list[str] = []
            for config in rejected:
                _task, model_name, prompt_version = config.key
                queue_or_recall = (
                    config.metrics.get("queue_accuracy")
                    if task == "triage"
                    else config.metrics.get("required_evidence_recall")
                )
                if queue_or_recall is None:
                    summary = "no primary metric"
                else:
                    summary = f"{queue_or_recall[0]}/{queue_or_recall[1]}"
                if config.disqualified:
                    note = "disqualified"
                elif config.failures:
                    note = f"{summary}, {config.failures} failed"
                else:
                    note = summary
                bits.append(
                    f"{model_name}/{_prompt_label(task, model_name, prompt_version)} ({note})"
                )
            lines.append(f"- rejected alternative(s): {'; '.join(bits)}")
        else:
            lines.append("- rejected alternative(s): none")
        lines.append(
            "- reopen when: a newer prompt version or model changes measured quality, "
            "latency, or boundary/PII outcomes on this 12-case corpus"
        )
        lines.append("")

    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text("\n".join(lines), encoding="utf-8")


def write_reports(
    *,
    run_id: str,
    models: Sequence[str],
    usage: Sequence[UsageRecord],
    outputs: Sequence[OutputRecord],
    scores: Sequence[ScoreRecord],
    report_path: Path,
    decision_path: Path,
) -> None:
    """Generate the comparison report and decision record for one run.

    Only records whose ``run_id`` matches the requested run are included.
    """

    run_usage = _for_run(usage, run_id)
    run_outputs = _for_run(outputs, run_id)
    run_scores = _for_run(scores, run_id)

    keys = _all_config_keys(run_usage, run_outputs, run_scores)
    stats_by_task: dict[str, list[_ConfigStats]] = defaultdict(list)
    for key in keys:
        task, _model, _prompt = key
        u = [row for row in run_usage if _key(row) == key]
        o = [row for row in run_outputs if _key(row) == key]
        s = [row for row in run_scores if _key(row) == key]
        stats_by_task[task].append(
            _config_stats(key=key, usage=u, outputs=o, scores=s)
        )

    decisions = {
        task: _select_config(task, configs) for task, configs in stats_by_task.items()
    }

    _write_report(
        run_id=run_id,
        usage=run_usage,
        outputs=run_outputs,
        scores=run_scores,
        report_path=Path(report_path),
        decisions=decisions,
    )

    _write_decision(
        run_id=run_id,
        models=models,
        usage=run_usage,
        outputs=run_outputs,
        scores=run_scores,
        decision_path=Path(decision_path),
        decisions=decisions,
        stats_by_task=stats_by_task,
    )
