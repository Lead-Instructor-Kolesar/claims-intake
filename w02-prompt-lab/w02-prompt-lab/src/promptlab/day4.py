"""Day 4: measurable triage routing through the prompt registry."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.prompts import load, render_user
from promptlab.records import OutputRecord, ScoreRecord, append_record
from promptlab.schemas import TriageOutput, TriageOutputWithAnalysis, schema_description
from promptlab.scoring import load_gold, score_output
from promptlab.structured import complete_structured
from promptlab.usage import CallRecord

PROMPT_ID = "triage"
TASK: Literal["triage"] = "triage"
MAX_OUTPUT_TOKENS = 1536
PROMPT_VERSIONS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("v1", TriageOutput),
    ("v2", TriageOutputWithAnalysis),
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


def render_system(system: str, schema: type[BaseModel]) -> str:
    return system.replace("{schema_description}", schema_description(schema))


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


def metric_ratio(scores: list[ScoreRecord], prompt_version: str, metric: str) -> str:
    rows = [
        score
        for score in scores
        if score.prompt_version == prompt_version and score.metric == metric
    ]
    numerator = sum(score.numerator for score in rows)
    denominator = sum(score.denominator for score in rows)
    return f"{numerator}/{denominator}"


def changed_queue_count(outputs: list[OutputRecord]) -> int:
    v1 = {
        record.case_id: (record.output or {}).get("queue")
        for record in outputs
        if record.prompt_version == "v1"
    }
    v2 = {
        record.case_id: (record.output or {}).get("queue")
        for record in outputs
        if record.prompt_version == "v2"
    }
    return sum(1 for case_id, queue in v1.items() if v2.get(case_id) != queue)


def token_and_latency(
    records: list[CallRecord], prompt_version: str
) -> tuple[int, int, float, int]:
    rows = [record for record in records if record.prompt_version == prompt_version]
    output_tokens = sum(record.output_tokens for record in rows)
    input_tokens = sum(record.input_tokens for record in rows)
    latencies = [record.latency_ms for record in rows]
    median_latency = float(median(latencies)) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0
    return output_tokens, input_tokens, median_latency, max_latency


def write_notes(
    path: Path,
    *,
    run_id: str,
    model_id: str,
    outputs: list[OutputRecord],
    scores: list[ScoreRecord],
    calls: list[CallRecord],
) -> None:
    v1_out, _, v1_med, v1_max = token_and_latency(calls, "v1")
    v2_out, _, v2_med, v2_max = token_and_latency(calls, "v2")
    delta = v2_out - v1_out
    queue_v1 = metric_ratio(scores, "v1", "queue")
    queue_v2 = metric_ratio(scores, "v2", "queue")
    queue_v1_n = int(queue_v1.split("/")[0])
    queue_v2_n = int(queue_v2.split("/")[0])
    gap = abs(queue_v2_n - queue_v1_n)
    if gap <= 1 and delta > 0:
        conclusion = (
            "v2's analysis field did not earn the extra output tokens or latency: "
            "queue accuracy moved by at most one case, which is too small to treat "
            "as a real gain."
        )
    elif queue_v2_n > queue_v1_n + 1:
        conclusion = (
            "v2's analysis field coincided with a queue-accuracy gain larger than "
            "one case, so the extra tokens and latency are at least worth another look."
        )
    else:
        conclusion = (
            "v2's analysis field did not improve routing enough to justify the extra "
            "tokens or latency on this 12-case set."
        )

    lines = [
        "# Day 4 notes",
        "",
        f"- Model: `{model_id}` at temperature `0.0`, one `run_id={run_id}`",
        f"- Observation count: {len(calls)} CallRecords in `runs/{run_id}.jsonl`",
        "- Cost: `$0.00` (local Ollama)",
        "",
        "## v1 (TriageOutput, no analysis)",
        f"- Queue: {queue_v1}",
        f"- Escalation: {metric_ratio(scores, 'v1', 'escalation')}",
        f"- Missed escalation: {metric_ratio(scores, 'v1', 'missed_escalation')}",
        f"- Unnecessary escalation: {metric_ratio(scores, 'v1', 'unnecessary_escalation')}",
        f"- Human boundary: {metric_ratio(scores, 'v1', 'human_boundary')}",
        f"- Output tokens: {v1_out}; median latency {v1_med:.0f} ms; max latency {v1_max} ms",
        "",
        "## v2 (TriageOutputWithAnalysis)",
        f"- Queue: {queue_v2}",
        f"- Escalation: {metric_ratio(scores, 'v2', 'escalation')}",
        f"- Missed escalation: {metric_ratio(scores, 'v2', 'missed_escalation')}",
        f"- Unnecessary escalation: {metric_ratio(scores, 'v2', 'unnecessary_escalation')}",
        f"- Human boundary: {metric_ratio(scores, 'v2', 'human_boundary')}",
        f"- Output tokens: {v2_out}; median latency {v2_med:.0f} ms; max latency {v2_max} ms",
        "",
        "## v1 vs v2",
        f"- Changed-queue count: {changed_queue_count(outputs)}/12",
        f"- Output-token delta (v2 - v1): {delta}",
        "",
        conclusion,
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_version(
    *,
    adapter: OllamaAdapter,
    cases: list[dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    prompt_version: str,
    schema: type[BaseModel],
    run_id: str,
    temperature: float,
    max_repairs: int,
    model_name: str,
) -> tuple[list[OutputRecord], list[ScoreRecord]]:
    template = load(PROMPT_ID, prompt_version)
    system = render_system(template.system, schema)
    outputs: list[OutputRecord] = []
    scores: list[ScoreRecord] = []

    for case in cases:
        case_id = str(case["id"])
        user_content = render_user(
            template,
            {"case_id": case_id},
            str(case["source"]),
        )
        request = CompletionRequest(
            task=TASK,
            case_id=case_id,
            prompt_id=PROMPT_ID,
            prompt_version=prompt_version,
            system=system,
            user_content=user_content,
            temperature=temperature,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        counter = CountingAdapter(adapter)
        error: str | None = None
        output: dict[str, Any] | None = None
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

        record = OutputRecord(
            run_id=run_id,
            task=TASK,
            case_id=case_id,
            model_name=model_name,
            model_id=adapter.model_id,
            prompt_version=prompt_version,
            succeeded=output is not None,
            repairs=max(0, counter.calls - 1),
            output=output,
            error=error,
        )
        outputs.append(record)
        scores.extend(
            score_output(
                run_id=run_id,
                case_id=case_id,
                model_name=model_name,
                prompt_version=prompt_version,
                output=output,
                gold=gold[case_id],
            )
        )
        print(
            f"{prompt_version} {case_id} succeeded={record.succeeded} "
            f"repairs={record.repairs} queue={(output or {}).get('queue')} "
            f"escalation={(output or {}).get('escalation_required')}"
            + (f" error={error[:180]}" if error else ""),
            flush=True,
        )
    return outputs, scores


def main() -> None:
    settings = Settings.from_env()
    run_id = str(uuid.uuid4())
    model = settings.models["mistral"]
    adapter = OllamaAdapter(model_id=model.model_id, base_url=settings.ollama_base_url)
    cases = load_cases(PROJECT_ROOT / "cases" / "triage.jsonl")
    gold = load_gold()

    all_outputs: list[OutputRecord] = []
    all_scores: list[ScoreRecord] = []
    for prompt_version, schema in PROMPT_VERSIONS:
        outputs, scores = run_version(
            adapter=adapter,
            cases=cases,
            gold=gold,
            prompt_version=prompt_version,
            schema=schema,
            run_id=run_id,
            temperature=0.0,
            max_repairs=settings.max_schema_repairs,
            model_name=model.logical_name,
        )
        all_outputs.extend(outputs)
        all_scores.extend(scores)

    docs_dir = PROJECT_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    run_path = docs_dir / "day4-run.jsonl"
    scores_path = docs_dir / "day4-scores.jsonl"
    for path in (run_path, scores_path):
        if path.exists():
            path.unlink()
    for output_record in all_outputs:
        append_record(run_path, output_record)
    for score_record in all_scores:
        append_record(scores_path, score_record)

    write_notes(
        docs_dir / "day4-notes.md",
        run_id=run_id,
        model_id=model.model_id,
        outputs=all_outputs,
        scores=all_scores,
        calls=load_call_records(run_id),
    )
    print(f"run_id={run_id}")
    print(f"queue_v1={metric_ratio(all_scores, 'v1', 'queue')}")
    print(f"queue_v2={metric_ratio(all_scores, 'v2', 'queue')}")


if __name__ == "__main__":
    main()
