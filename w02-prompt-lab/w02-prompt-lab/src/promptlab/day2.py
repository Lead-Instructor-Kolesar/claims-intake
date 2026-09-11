"""Day 2: the same summarization request, two configured local models."""

from __future__ import annotations

import json
import statistics
from typing import Any
from uuid import uuid4

from promptlab.adapters.base import CompletionRequest
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.usage import CallRecord, append_record

PROMPT_ID = "baseline"
PROMPT_VERSION = "v0"
# One ceiling for both models. A short cap gets spent before one model stops,
# so the shared limit is high enough that the comparison is not just truncation.
MAX_OUTPUT_TOKENS = 1024
CASES_PATH = PROJECT_ROOT / "cases" / "summarization.jsonl"
PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "baseline.v0.md"
DOCS_RUN_PATH = PROJECT_ROOT / "docs" / "day2-run.jsonl"
DOCS_COMPARISON_PATH = PROJECT_ROOT / "docs" / "day2-comparison.md"


def load_cases() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in CASES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("summarization case file has a non-object row")
            rows.append(row)
    return rows


def split_prompt(template: str, source: str) -> tuple[str, str]:
    rendered = template.replace("{document_text}", source)
    marker = "<document>"
    if marker not in rendered:
        return "", rendered
    system, _, rest = rendered.partition(marker)
    return system.strip(), f"{marker}{rest}".strip()


def build_request(
    case: dict[str, Any],
    system: str,
    user_content: str,
    temperature: float,
) -> CompletionRequest:
    return CompletionRequest(
        task=case["task"],
        case_id=str(case["id"]),
        prompt_id=PROMPT_ID,
        prompt_version=PROMPT_VERSION,
        system=system,
        user_content=user_content,
        temperature=temperature,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def summarize(records: list[CallRecord]) -> str:
    if not records:
        return "No model calls were recorded.\n"

    groups = _grouped(records)
    lines = [
        "# Day 2 model comparison",
        "",
        f"Run id: {records[0].run_id}",
        (
            f"{_shared_count(records, 'case_id')} summarization cases ran through "
            f"baseline {records[0].prompt_version} at temperature "
            f"{_format_number(records[0].temperature)}, with a max output of "
            f"{records[0].max_output_tokens} tokens."
        ),
        "Both models used provider ollama and are distinguished by the configured model id.",
        _cost_line(records),
        "",
    ]

    stats = [_stats(group) for group in groups]
    for item in stats:
        lines.extend(
            [
                f"## {item['model_id']}",
                "",
                f"- successes: {item['successes']}",
                f"- attempts: {item['attempts']}",
                f"- failures: {item['failures']}",
                f"- truncations: {item['truncations']}",
                f"- input tokens: {item['input_tokens']}",
                f"- output tokens: {item['output_tokens']}",
                f"- median latency: {_ms(item['median_latency_ms'])} ms",
                f"- max latency: {item['max_latency_ms']} ms",
                "",
            ]
        )

    lines.extend(["## Observation", "", _observation(stats), ""])
    return "\n".join(lines)


def main() -> None:
    settings = Settings.from_env()
    template = PROMPT_PATH.read_text(encoding="utf-8")
    run_id = str(uuid4())
    prepared = [(case, *split_prompt(template, str(case["source"]))) for case in load_cases()]
    collected: list[CallRecord] = []

    for model in settings.models.values():
        adapter = OllamaAdapter(model_id=model.model_id, base_url=settings.ollama_base_url)
        for case, system, user_content in prepared:
            request = build_request(case, system, user_content, settings.temperature)
            result = adapter.complete(request, run_id)
            if not result.records:
                print(f"{request.case_id}: no attempt recorded")
                continue
            for record in result.records:
                append_record(record, run_id)
                collected.append(record)
            last = result.records[-1]
            print(
                f"{last.case_id} {last.model_id}: "
                f"{last.input_tokens} in / {last.output_tokens} out / "
                f"{last.latency_ms} ms error={last.error_type}"
            )

    _write_docs(collected)
    print(f"wrote {DOCS_RUN_PATH}")
    print(f"wrote {DOCS_COMPARISON_PATH}")


def _write_docs(records: list[CallRecord]) -> None:
    DOCS_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(record.model_dump_json() + "\n" for record in records)
    DOCS_RUN_PATH.write_text(body, encoding="utf-8")
    DOCS_COMPARISON_PATH.write_text(summarize(records), encoding="utf-8")


def _grouped(records: list[CallRecord]) -> list[list[CallRecord]]:
    order: list[str] = []
    buckets: dict[str, list[CallRecord]] = {}
    for record in records:
        if record.model_id not in buckets:
            order.append(record.model_id)
            buckets[record.model_id] = []
        buckets[record.model_id].append(record)
    return [buckets[model_id] for model_id in order]


def _stats(group: list[CallRecord]) -> dict[str, Any]:
    latencies = [record.latency_ms for record in group]
    successes = sum(record.error_type is None for record in group)
    return {
        "model_id": group[0].model_id,
        "attempts": len(group),
        "successes": successes,
        "failures": len(group) - successes,
        "truncations": sum(record.error_type == "TruncatedResponseError" for record in group),
        "input_tokens": sum(record.input_tokens for record in group),
        "output_tokens": sum(record.output_tokens for record in group),
        "median_latency_ms": float(statistics.median(latencies)),
        "max_latency_ms": max(latencies),
    }


def _observation(stats: list[dict[str, Any]]) -> str:
    if len(stats) < 2:
        only = stats[0]
        return (
            f"{only['model_id']} recorded {only['successes']} successes in "
            f"{only['attempts']} attempts. A second configured model is needed "
            f"before this run can compare models."
        )

    left, right = stats[0], stats[1]
    heavier = left if left["output_tokens"] >= right["output_tokens"] else right
    lighter = right if heavier is left else left
    out_ratio = _ratio(heavier["output_tokens"], lighter["output_tokens"])
    lat_ratio = _ratio(heavier["median_latency_ms"], lighter["median_latency_ms"])
    sentences = [
        (
            f"{heavier['model_id']} used {out_ratio} times the output tokens of "
            f"{lighter['model_id']} and {lat_ratio} times the median latency on the "
            "same twelve cases."
        ),
        (
            f"Input tokens stayed close ({left['input_tokens']} vs {right['input_tokens']}), "
            "so the extra wall time tracks longer generation rather than a billed API."
        ),
    ]
    for item in (left, right):
        if item["truncations"]:
            sentences.append(
                f"{item['model_id']} had {item['truncations']} truncated attempts, "
                "so those outputs hit the token ceiling."
            )
    return " ".join(sentences)


def _cost_line(records: list[CallRecord]) -> str:
    if all(record.cost_usd == 0.0 for record in records):
        return (
            "Every recorded cost_usd is 0.0. Local Ollama has no per-token provider "
            "charge, so this note does not compare dollar cost."
        )
    return "Recorded cost_usd values were not all 0.0. This note still does not invent a price."


def _shared_count(records: list[CallRecord], field: str) -> int:
    return len({getattr(record, field) for record in records})


def _ms(value: float) -> str:
    return _format_number(value)


def _ratio(numerator: float, denominator: float) -> str:
    if denominator == 0:
        return "n/a"
    return _format_number(numerator / denominator)


def _format_number(value: float) -> str:
    rounded = round(float(value), 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"


if __name__ == "__main__":
    main()
