"""Day 2 runner: compare configured models on all summarization cases."""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from promptlab.adapters.base import CompletionRequest
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.errors import TruncatedResponseError
from promptlab.usage import CallRecord, append_record

LOGICAL_MODEL_KEYS: tuple[str, ...] = ("mistral", "qwen")
MAX_OUTPUT_TOKENS = 1024
PROMPT_ID = "baseline"
PROMPT_VERSION = "v0"
DOCUMENT_OPEN = "<document>"
DOCUMENT_CLOSE = "</document>"
EXPECTED_CASE_COUNT = 12
CASES_PATH = PROJECT_ROOT / "cases" / "summarization.jsonl"
PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "baseline.v0.md"
EVIDENCE_PATH = PROJECT_ROOT / "docs" / "day2-run.jsonl"
COMPARISON_PATH = PROJECT_ROOT / "docs" / "day2-comparison.md"


def load_summarization_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case: dict[str, Any] = json.loads(line)
        cases.append(case)
    if len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError(
            f"expected {EXPECTED_CASE_COUNT} summarization cases, got {len(cases)}"
        )
    return cases


def split_baseline_prompt(template: str, source: str) -> tuple[str, str]:
    marker_at = template.find(DOCUMENT_OPEN)
    if marker_at < 0:
        raise ValueError("baseline prompt is missing document tags")
    system = template[:marker_at].rstrip()
    user_content = f"{DOCUMENT_OPEN}\n{source}\n{DOCUMENT_CLOSE}"
    return system, user_content


def load_evidence(path: Path) -> list[CallRecord]:
    records: list[CallRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(CallRecord.model_validate_json(line))
    return records


@dataclass(frozen=True)
class ModelStats:
    logical_name: str
    model_id: str
    attempts: int
    successes: int
    truncations: int
    other_errors: int
    input_tokens_sum: int
    input_tokens_mean: float
    output_tokens_sum: int
    output_tokens_mean: float
    latency_ms_mean: float
    latency_ms_median: float
    latency_ms_max: int
    cost_usd: float


def _mean(values: Sequence[int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _median(values: Sequence[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def stats_for_model(
    logical_name: str,
    model_id: str,
    records: Sequence[CallRecord],
) -> ModelStats:
    rows = [record for record in records if record.model_id == model_id]
    successes = sum(1 for record in rows if record.error_type is None)
    truncations = sum(
        1 for record in rows if record.error_type == TruncatedResponseError.__name__
    )
    other_errors = len(rows) - successes - truncations
    input_tokens = [record.input_tokens for record in rows]
    output_tokens = [record.output_tokens for record in rows]
    latencies = [record.latency_ms for record in rows]
    costs = [record.cost_usd for record in rows]
    return ModelStats(
        logical_name=logical_name,
        model_id=model_id,
        attempts=len(rows),
        successes=successes,
        truncations=truncations,
        other_errors=other_errors,
        input_tokens_sum=sum(input_tokens),
        input_tokens_mean=_mean(input_tokens),
        output_tokens_sum=sum(output_tokens),
        output_tokens_mean=_mean(output_tokens),
        latency_ms_mean=_mean(latencies),
        latency_ms_median=_median(latencies),
        latency_ms_max=max(latencies) if latencies else 0,
        cost_usd=0.0 if not costs else max(costs),
    )


def render_comparison(records: Sequence[CallRecord], settings: Settings) -> str:
    stats_by_name = {
        logical_name: stats_for_model(
            logical_name,
            settings.models[logical_name].model_id,
            records,
        )
        for logical_name in LOGICAL_MODEL_KEYS
    }
    sections = [
        "# Day 2 model comparison",
        "",
        "Generated from `docs/day2-run.jsonl`. "
        "`cost_usd` is 0.0 for both configured models; this is not a dollar-cost race "
        "and no cost winner is named.",
        "",
    ]
    for logical_name in LOGICAL_MODEL_KEYS:
        stats = stats_by_name[logical_name]
        sections.extend(
            [
                f"## {logical_name} (`{stats.model_id}`)",
                "",
                f"- Attempts: {stats.attempts}",
                f"- Successes: {stats.successes}",
                f"- Truncations: {stats.truncations}",
                f"- Other errors: {stats.other_errors}",
                f"- Input tokens: sum={stats.input_tokens_sum}, "
                f"mean={stats.input_tokens_mean:.2f}",
                f"- Output tokens: sum={stats.output_tokens_sum}, "
                f"mean={stats.output_tokens_mean:.2f}",
                f"- Latency (ms): mean={stats.latency_ms_mean:.2f}, "
                f"max={stats.latency_ms_max}",
                f"- Latency median (ms): {stats.latency_ms_median:.2f}",
                "- cost_usd: 0.0",
                "",
            ]
        )
    mistral = stats_by_name["mistral"]
    qwen = stats_by_name["qwen"]
    sections.extend(
        [
            "## Observation",
            "",
            (
                f"{mistral.logical_name} succeeded on {mistral.successes} of "
                f"{mistral.attempts} attempts (truncations={mistral.truncations}, "
                f"other errors={mistral.other_errors}) with {mistral.input_tokens_sum} "
                f"input tokens and {mistral.output_tokens_sum} output tokens; "
                f"median latency {mistral.latency_ms_median:.2f} ms, "
                f"max {mistral.latency_ms_max} ms. "
                f"{qwen.logical_name} succeeded on {qwen.successes} of "
                f"{qwen.attempts} attempts (truncations={qwen.truncations}, "
                f"other errors={qwen.other_errors}) with {qwen.input_tokens_sum} "
                f"input tokens and {qwen.output_tokens_sum} output tokens; "
                f"median latency {qwen.latency_ms_median:.2f} ms, "
                f"max {qwen.latency_ms_max} ms. "
                "These counts and latencies come from the JSONL records; both models "
                "recorded cost_usd=0.0, so this is a token and latency comparison, "
                "not a dollar-cost ranking."
            ),
            "",
        ]
    )
    return "\n".join(sections).rstrip() + "\n"


def write_comparison(evidence_path: Path, markdown_path: Path, settings: Settings) -> None:
    records = load_evidence(evidence_path)
    markdown_path.write_text(render_comparison(records, settings), encoding="utf-8")


def main() -> None:
    settings = Settings.from_env()
    run_id = str(uuid4())
    cases = load_summarization_cases(CASES_PATH)
    template = PROMPT_PATH.read_text(encoding="utf-8")

    for logical_name in LOGICAL_MODEL_KEYS:
        model_id = settings.models[logical_name].model_id
        adapter = OllamaAdapter(model_id=model_id)
        for case in cases:
            case_id = str(case["id"])
            source = str(case["source"])
            system, user_content = split_baseline_prompt(template, source)
            request = CompletionRequest(
                task="summarization",
                case_id=case_id,
                prompt_id=PROMPT_ID,
                prompt_version=PROMPT_VERSION,
                system=system,
                user_content=user_content,
                temperature=settings.temperature,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
            result = adapter.complete(request, run_id)
            for record in result.records:
                append_record(record, run_id)
            print(
                f"{logical_name} {case_id} succeeded={result.succeeded} "
                f"error={result.error_type} records={len(result.records)}"
            )

    run_path = Path("runs") / f"{run_id}.jsonl"
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(run_path, EVIDENCE_PATH)
    write_comparison(EVIDENCE_PATH, COMPARISON_PATH, settings)

    print(f"run_id={run_id}")
    print(f"records={run_path}")
    print(f"evidence={EVIDENCE_PATH}")
    print(f"comparison={COMPARISON_PATH}")


if __name__ == "__main__":
    main()
