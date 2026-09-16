"""Write comparison and model-decision reports from recorded evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from statistics import median

from promptlab.records import OutputRecord, ScoreRecord, UsageRecord

TRANSFER_MODELS = frozenset({"qwen"})


def _ratio(scores: Iterable[ScoreRecord], metric: str) -> str:
    rows = [score for score in scores if score.metric == metric]
    if not rows:
        return "n/a"
    return f"{sum(score.numerator for score in rows)}/{sum(score.denominator for score in rows)}"


def _prompt_label(model_name: str, prompt_version: str, prompt_id: str) -> str:
    base = f"{prompt_id}.{prompt_version}"
    if model_name in TRANSFER_MODELS:
        return f"{base} transfer"
    return base


def _task_prompt_id(task: str) -> str:
    return {"summarization": "summarize", "extraction": "extract", "triage": "triage"}[task]


def _quality_cell(task: str, rows: list[ScoreRecord]) -> str:
    if task == "triage":
        return (
            f"queue {_ratio(rows, 'queue')}; "
            f"escalation {_ratio(rows, 'escalation')}; "
            f"missed {_ratio(rows, 'missed_escalation')}; "
            f"unnecessary {_ratio(rows, 'unnecessary_escalation')}; "
            f"boundary {_ratio(rows, 'human_boundary_compliance')}; "
            f"PII {_ratio(rows, 'pii_leakage')}"
        )
    if task == "extraction":
        return (
            f"required {_ratio(rows, 'required_evidence_recall')}; "
            f"citation {_ratio(rows, 'citation_correctness')}; "
            f"unsupported-avoided {_ratio(rows, 'unsupported_field_avoidance')}"
        )
    return (
        f"required {_ratio(rows, 'required_evidence_recall')}; "
        f"citation {_ratio(rows, 'citation_correctness')}"
    )


def write_reports(
    *,
    run_id: str,
    models: list[str],
    usage: list[UsageRecord],
    outputs: list[OutputRecord],
    scores: list[ScoreRecord],
    report_path: Path,
    decision_path: Path,
) -> None:
    grouped_scores: dict[tuple[str, str, str], list[ScoreRecord]] = defaultdict(list)
    for score in scores:
        grouped_scores[(score.task, score.model_name, score.prompt_version)].append(score)

    grouped_usage: dict[tuple[str, str, str], list[UsageRecord]] = defaultdict(list)
    for record in usage:
        grouped_usage[(record.task, record.model_name, record.prompt_version)].append(record)

    grouped_outputs: dict[tuple[str, str, str], list[OutputRecord]] = defaultdict(list)
    for output_record in outputs:
        grouped_outputs[
            (output_record.task, output_record.model_name, output_record.prompt_version)
        ].append(output_record)

    lines = [
        "# Local Model Comparison",
        "",
        f"Run `{run_id}` compared configured Ollama models. Local provider/API cost is `$0.00`.",
        "Qwen rows are prompt-transfer: the same Day 3/4 prompt versions, not Qwen-tuned variants.",
        "",
    ]
    tasks = ("summarization", "extraction", "triage")
    for task in tasks:
        prompt_id = _task_prompt_id(task)
        lines.extend(
            [
                f"## {task}",
                "",
                "| Model | Prompt | Quality | Input tokens/case | "
                "Output tokens/case | Median latency | Max latency | "
                "Repairs | Observations |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for model_name in models:
            keys = [
                key
                for key in grouped_outputs
                if key[0] == task and key[1] == model_name
            ]
            if not keys:
                continue
            _, _, prompt_version = keys[0]
            key = (task, model_name, prompt_version)
            score_rows = grouped_scores.get(key, [])
            usage_rows = grouped_usage.get(key, [])
            output_rows = grouped_outputs.get(key, [])
            n = max(len(output_rows), 1)
            input_tokens = sum(row.prompt_tokens for row in usage_rows)
            output_tokens = sum(row.completion_tokens for row in usage_rows)
            latencies = [row.latency_ms for row in usage_rows]
            median_latency = float(median(latencies)) if latencies else 0.0
            max_latency = max(latencies) if latencies else 0.0
            repaired = sum(1 for row in output_rows if row.repairs > 0)
            lines.append(
                "| "
                + " | ".join(
                    [
                        model_name,
                        _prompt_label(model_name, prompt_version, prompt_id),
                        _quality_cell(task, score_rows),
                        f"{input_tokens / n:.1f}",
                        f"{output_tokens / n:.1f}",
                        f"{median_latency:.0f} ms",
                        f"{max_latency:.0f} ms",
                        f"{repaired}/{len(output_rows) or 1}",
                        str(len(usage_rows)),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(
        [
            "## Limits",
            "",
            "- There are only 12 cases per task.",
            "  Results are directional, not production-scale estimates.",
            "- Qwen rows are labeled prompt-transfer.",
            "  No Qwen-adapted prompt version was introduced.",
            "- Untested combinations: any prompt besides `summarize.v1`,",
            "  `extract.v2`, and `triage.v1`; temperatures other than 0.0;",
            "  models other than the two configured Ollama identities.",
            "- No production-volume reliability claim is being made.",
            "- Local Ollama latency depends on lab hardware.",
            "- Do not treat an 11/12 vs 10/12 gap as a universal model ranking.",
            "",
            "## Recommendation",
            "",
        ]
    )
    lines.extend(_recommendations(models, grouped_scores))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    decision_lines = [
        "# Model Decision Record",
        "",
        "## evidence",
        "",
        f"- run_id: `{run_id}`",
        "- provider: ollama; cost_usd: $0.00",
        "- prompts: summarization=`summarize.v1`, extraction=`extract.v2`, triage=`triage.v1`",
        "- Qwen used those exact versions as a prompt-transfer test",
        f"- models compared: {', '.join(models)}",
        "",
        "## decision",
        "",
    ]
    decision_lines.extend(_decision_bullets(models))
    decision_lines.extend(
        [
            "",
            "## rejected alternatives",
            "",
            "- Inventing a cloud token price for local Ollama models",
            "- Asking the model which policy version is current",
            "  instead of `select_current_version`",
            "- Switching triage to `triage.v2`; Day 4 showed the same 10/12",
            "  queue with extra output tokens",
            "- Treating Qwen transfer scores as proof that Qwen is worse at extraction in general",
            "",
            "## review triggers",
            "",
            "- A new gold case set larger than n=12",
            "- A Qwen-adapted prompt version with its own recorded run",
            "- Human-boundary failure on either model",
            "- Material change to schema, adapter, or temperature",
            "",
        ]
    )
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text("\n".join(decision_lines), encoding="utf-8")


def _queue_ratio(rows: list[ScoreRecord]) -> tuple[int, int]:
    selected = [row for row in rows if row.metric in {"queue", "required_evidence_recall"}]
    if not selected:
        selected = [row for row in rows if row.metric == "queue_accuracy"]
    return sum(row.numerator for row in selected), sum(row.denominator for row in selected)


def _recommendations(
    models: list[str],
    grouped_scores: dict[tuple[str, str, str], list[ScoreRecord]],
) -> list[str]:
    lines: list[str] = []
    for task in ("summarization", "extraction", "triage"):
        prompt_id = _task_prompt_id(task)
        best_model = models[0] if models else "mistral"
        best_score = (-1, 0)
        prompt_version = "v1" if task != "extraction" else "v2"
        for model_name in models:
            keys = [key for key in grouped_scores if key[0] == task and key[1] == model_name]
            if not keys:
                continue
            prompt_version = keys[0][2]
            num, den = _queue_ratio(grouped_scores[keys[0]])
            if den and num / den > (best_score[0] / best_score[1] if best_score[1] else -1):
                best_score = (num, den)
                best_model = model_name
        lines.append(
            f"- **{task}**: model `{best_model}`, prompt `{prompt_id}.{prompt_version}`"
            + (" transfer" if best_model in TRANSFER_MODELS else "")
            + f". Headline quality {best_score[0]}/{best_score[1] or 1} on this 12-case set. "
            "Reopen if a larger gold set or a model-specific prompt version is recorded."
        )
    return lines


def _decision_bullets(models: list[str]) -> list[str]:
    return [
        "- Keep both configured Ollama models available;",
        "  recommend per task from the comparison tables.",
        "- Use `summarize.v1`, `extract.v2`, and `triage.v1`",
        "  until a later recorded version beats them on gold.",
        f"- Models in this record: {', '.join(models)}.",
    ]
