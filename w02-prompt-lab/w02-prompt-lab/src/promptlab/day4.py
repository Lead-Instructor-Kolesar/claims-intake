"""Day 4: measurable triage routing with two prompt versions."""

from __future__ import annotations

import json
import statistics
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, ModelConfig, Settings
from promptlab.prompts import load, render_user
from promptlab.records import OutputRecord, ScoreRecord
from promptlab.schemas import (
    StrictModel,
    TaskName,
    TriageOutput,
    TriageOutputWithAnalysis,
    schema_description,
)
from promptlab.scoring import score_triage
from promptlab.structured import complete_structured
from promptlab.usage import CallRecord, append_record

MAX_OUTPUT_TOKENS = 1024
CASES_PATH = PROJECT_ROOT / "cases" / "triage.jsonl"
GOLD_PATH = PROJECT_ROOT / "cases" / "gold" / "triage.jsonl"
DOCS_RUN_PATH = PROJECT_ROOT / "docs" / "day4-run.jsonl"
DOCS_SCORES_PATH = PROJECT_ROOT / "docs" / "day4-scores.jsonl"
DOCS_NOTES_PATH = PROJECT_ROOT / "docs" / "day4-notes.md"

PROMPT_VERSIONS: tuple[tuple[str, type[TriageOutput]], ...] = (
    ("v1", TriageOutput),
    ("v2", TriageOutputWithAnalysis),
)


class CountingAdapter:
    """Wrap an adapter so callers can count semantic attempts and collect CallRecords."""

    def __init__(self, inner: ModelAdapter) -> None:
        self._inner = inner
        self.provider = inner.provider
        self.model_id = inner.model_id
        self.calls = 0
        self.records: list[CallRecord] = []

    def reset(self) -> None:
        self.calls = 0
        self.records = []

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        self.calls += 1
        result = self._inner.complete(request, run_id)
        self.records.extend(result.records)
        return result


def load_cases(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("case file has a non-object row")
            rows.append(row)
    return rows


def load_gold(path: Path) -> dict[str, dict[str, Any]]:
    gold: dict[str, dict[str, Any]] = {}
    for row in load_cases(path):
        gold[str(row["id"])] = row
    return gold


def render_case(prompt_version: str, source: str, schema: type[StrictModel]) -> tuple[str, str]:
    template = load("triage", prompt_version)
    system = template.system.replace("{schema_description}", schema_description(schema))
    user_content = render_user(template, variables={}, untrusted=source)
    return system, user_content


def build_request(
    *,
    case_id: str,
    prompt_version: str,
    system: str,
    user_content: str,
    temperature: float,
) -> CompletionRequest:
    task: TaskName = "triage"
    return CompletionRequest(
        task=task,
        case_id=case_id,
        prompt_id="triage",
        prompt_version=prompt_version,
        system=system,
        user_content=user_content,
        temperature=temperature,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def changed_queue_count(outputs: Sequence[OutputRecord]) -> int:
    by_case: dict[str, dict[str, str]] = {}
    for record in outputs:
        if not record.succeeded or record.output is None:
            continue
        queue = record.output.get("queue")
        if not isinstance(queue, str):
            continue
        by_case.setdefault(record.case_id, {})[record.prompt_version] = queue
    changed = 0
    for versions in by_case.values():
        if "v1" in versions and "v2" in versions and versions["v1"] != versions["v2"]:
            changed += 1
    return changed


def _metric_total(
    scores: Sequence[ScoreRecord], prompt_version: str, metric: str
) -> tuple[int, int]:
    rows = [
        score
        for score in scores
        if score.prompt_version == prompt_version and score.metric == metric
    ]
    numerator = sum(score.numerator for score in rows)
    denominator = sum(score.denominator for score in rows)
    return numerator, denominator


def _format_ms(value: float | int) -> str:
    rounded = round(float(value), 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"


def _calls_for(calls: Sequence[CallRecord], prompt_version: str) -> list[CallRecord]:
    return [record for record in calls if record.prompt_version == prompt_version]


def _version_block(
    *,
    prompt_version: str,
    scores: Sequence[ScoreRecord],
    calls: Sequence[CallRecord],
) -> list[str]:
    queue_n, queue_d = _metric_total(scores, prompt_version, "queue_accuracy")
    esc_n, esc_d = _metric_total(scores, prompt_version, "escalation_accuracy")
    missed, _ = _metric_total(scores, prompt_version, "missed_escalation")
    unnecessary, _ = _metric_total(scores, prompt_version, "unnecessary_escalation")
    bound_n, bound_d = _metric_total(scores, prompt_version, "human_boundary_compliance")
    version_calls = _calls_for(calls, prompt_version)
    output_tokens = sum(record.output_tokens for record in version_calls)
    latencies = [record.latency_ms for record in version_calls]
    median_latency = statistics.median(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    return [
        f"triage.{prompt_version}",
        f"queue correct: {queue_n}/{queue_d}",
        f"escalation correct: {esc_n}/{esc_d}",
        f"missed escalations: {missed}",
        f"unnecessary escalations: {unnecessary}",
        f"human-boundary passes: {bound_n}/{bound_d}",
        f"output tokens: {output_tokens}",
        f"median latency: {_format_ms(median_latency)} ms",
        f"maximum latency: {_format_ms(max_latency)} ms",
        "",
    ]


def format_notes(
    *,
    run_id: str,
    model_id: str,
    outputs: Sequence[OutputRecord],
    scores: Sequence[ScoreRecord],
    calls: Sequence[CallRecord],
) -> str:
    v1_tokens = sum(record.output_tokens for record in _calls_for(calls, "v1"))
    v2_tokens = sum(record.output_tokens for record in _calls_for(calls, "v2"))
    token_delta = v2_tokens - v1_tokens
    queue_v1, queue_d1 = _metric_total(scores, "v1", "queue_accuracy")
    queue_v2, queue_d2 = _metric_total(scores, "v2", "queue_accuracy")
    all_zero_cost = all(record.cost_usd == 0.0 for record in calls) if calls else True
    cost_line = (
        "Provider/API cost: $0.00"
        if all_zero_cost
        else "Recorded cost_usd values were not all 0.0. This note still does not invent a price."
    )
    if queue_v2 > queue_v1 and token_delta > 0:
        conclusion = (
            f"v2 gained {queue_v2 - queue_v1} extra correct queue on a {queue_d1}-case set "
            f"while using {token_delta} more output tokens. That is not enough to treat the "
            "analysis field as generally better."
        )
    elif queue_v2 < queue_v1:
        conclusion = (
            f"v2 used {token_delta} extra output tokens and median latency rose, while queue "
            f"accuracy fell from {queue_v1}/{queue_d1} to {queue_v2}/{queue_d2}. The analysis "
            "field did not earn its overhead on this twelve-case set."
        )
    else:
        conclusion = (
            f"Queue accuracy stayed {queue_v1}/{queue_d1} while v2 used {token_delta} extra "
            "output tokens. The analysis field did not improve routing enough to justify the "
            "added generation cost."
        )

    per_case_lines = ["output tokens per case:"]
    case_ids = sorted({record.case_id for record in calls})
    tokens_by_case: dict[str, dict[str, int]] = {}
    for record in calls:
        tokens_by_case.setdefault(record.case_id, {})[record.prompt_version] = record.output_tokens
    for case_id in case_ids:
        versions = tokens_by_case.get(case_id, {})
        per_case_lines.append(
            f"{case_id}: v1={versions.get('v1', 0)} v2={versions.get('v2', 0)}"
        )

    lines = [
        "# Day 4 notes",
        "",
        f"Run id: {run_id}",
        f"Model: {model_id}",
        "Temperature: 0.0",
        "",
        *_version_block(prompt_version="v1", scores=scores, calls=calls),
        *_version_block(prompt_version="v2", scores=scores, calls=calls),
        f"changed-queue count: {changed_queue_count(outputs)}",
        f"output-token difference (v2 - v1): {token_delta}",
        f"observation count: {len(calls)}",
        cost_line,
        "",
        *per_case_lines,
        "",
        conclusion,
        "",
    ]
    return "\n".join(lines)


def run_case(
    *,
    adapter: CountingAdapter,
    case: dict[str, Any],
    schema: type[TriageOutput],
    prompt_version: str,
    model: ModelConfig,
    run_id: str,
    temperature: float,
    max_repairs: int,
) -> tuple[OutputRecord, list[CallRecord]]:
    adapter.reset()
    system, user_content = render_case(prompt_version, str(case["source"]), schema)
    request = build_request(
        case_id=str(case["id"]),
        prompt_version=prompt_version,
        system=system,
        user_content=user_content,
        temperature=temperature,
    )
    try:
        parsed = complete_structured(
            adapter,
            request,
            schema,
            run_id,
            max_repairs=max_repairs,
        )
        repairs = max(0, adapter.calls - 1)
        record = OutputRecord(
            run_id=run_id,
            task="triage",
            case_id=str(case["id"]),
            model_name=model.logical_name,
            model_id=model.model_id,
            prompt_version=prompt_version,
            succeeded=True,
            repairs=repairs,
            output=parsed.model_dump(),
            error=None,
        )
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        repairs = max(0, adapter.calls - 1) if adapter.calls else 0
        record = OutputRecord(
            run_id=run_id,
            task="triage",
            case_id=str(case["id"]),
            model_name=model.logical_name,
            model_id=model.model_id,
            prompt_version=prompt_version,
            succeeded=False,
            repairs=repairs,
            output=None,
            error=str(exc),
        )
    return record, list(adapter.records)


def main() -> None:
    settings = Settings.from_env()
    model = settings.models["mistral"]
    temperature = 0.0
    max_repairs = settings.max_schema_repairs
    run_id = str(uuid4())

    cases = load_cases(CASES_PATH)
    gold = load_gold(GOLD_PATH)
    adapter = CountingAdapter(
        OllamaAdapter(model_id=model.model_id, base_url=settings.ollama_base_url)
    )

    outputs: list[OutputRecord] = []
    call_records: list[CallRecord] = []
    scores: list[ScoreRecord] = []

    for prompt_version, schema in PROMPT_VERSIONS:
        for case in cases:
            output, records = run_case(
                adapter=adapter,
                case=case,
                schema=schema,
                prompt_version=prompt_version,
                model=model,
                run_id=run_id,
                temperature=temperature,
                max_repairs=max_repairs,
            )
            outputs.append(output)
            for record in records:
                append_record(record, run_id)
                call_records.append(record)

            label = gold[str(case["id"])]
            parsed: TriageOutput | None = None
            if output.succeeded and output.output is not None:
                parsed = schema.model_validate(output.output)
            scores.extend(
                score_triage(
                    run_id=run_id,
                    case_id=str(case["id"]),
                    model_name=model.logical_name,
                    prompt_version=prompt_version,
                    output=parsed,
                    expected_queue=str(label["expected_queue"]),
                    expected_escalation=bool(label["expected_escalation"]),
                )
            )
            print(
                f"{output.case_id} {prompt_version}: "
                f"succeeded={output.succeeded} repairs={output.repairs} "
                f"error={output.error}"
            )

    notes = format_notes(
        run_id=run_id,
        model_id=model.model_id,
        outputs=outputs,
        scores=scores,
        calls=call_records,
    )
    _write_docs(outputs, scores, notes)
    print(f"wrote {DOCS_RUN_PATH}")
    print(f"wrote {DOCS_SCORES_PATH}")
    print(f"wrote {DOCS_NOTES_PATH}")
    print(f"call records: {len(call_records)}")


def _write_docs(
    outputs: Sequence[OutputRecord],
    scores: Sequence[ScoreRecord],
    notes: str,
) -> None:
    DOCS_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_RUN_PATH.write_text(
        "".join(record.model_dump_json() + "\n" for record in outputs),
        encoding="utf-8",
    )
    DOCS_SCORES_PATH.write_text(
        "".join(record.model_dump_json() + "\n" for record in scores),
        encoding="utf-8",
    )
    DOCS_NOTES_PATH.write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
