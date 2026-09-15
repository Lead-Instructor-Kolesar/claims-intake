"""Day 4 runner: two triage prompt versions, one model, deterministic scores.

Runs prompts/triage.v1.md and prompts/triage.v2.md over cases/triage.jsonl
under one run_id through complete_structured, then writes run, score, and
notes evidence. The experimental variable is the prompt version.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from promptlab.adapters.base import CompletionRequest
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.prompts import load, render_user, substitute
from promptlab.records import OutputRecord, ScoreRecord
from promptlab.records import append_record as append_output_record
from promptlab.schemas import (
    TriageOutput,
    TriageOutputWithAnalysis,
    schema_description,
)
from promptlab.scoring import (
    METRIC_ESCALATION,
    METRIC_HUMAN_BOUNDARY,
    METRIC_MISSED_ESCALATION,
    METRIC_QUEUE,
    METRIC_UNNECESSARY_ESCALATION,
    score_case,
)
from promptlab.structured import (
    StructuredCallTrace,
    StructuredCompletionError,
    complete_structured,
)
from promptlab.usage import CallRecord
from promptlab.usage import append_record as append_call_record

LOGICAL_MODEL_KEY = "mistral"
MAX_OUTPUT_TOKENS = 1024
EXPECTED_CASE_COUNT = 12
PROMPT_ID = "triage"
TEMPERATURE = 0.0

CASES_PATH = PROJECT_ROOT / "cases" / "triage.jsonl"
GOLD_PATH = PROJECT_ROOT / "cases" / "gold" / "triage.jsonl"
RUNS_DIR = PROJECT_ROOT / "runs"
EVIDENCE_PATH = PROJECT_ROOT / "docs" / "day4-run.jsonl"
SCORES_PATH = PROJECT_ROOT / "docs" / "day4-scores.jsonl"
NOTES_PATH = PROJECT_ROOT / "docs" / "day4-notes.md"


@dataclass(frozen=True)
class PromptVersion:
    version: str
    schema: type[BaseModel]


PROMPT_VERSIONS: tuple[PromptVersion, ...] = (
    PromptVersion("v1", TriageOutput),
    PromptVersion("v2", TriageOutputWithAnalysis),
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row: dict[str, Any] = json.loads(line)
        rows.append(row)
    return rows


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = load_jsonl(path)
    if len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError(
            f"expected {EXPECTED_CASE_COUNT} cases in {path.name}, got {len(cases)}"
        )
    return cases


def load_gold(path: Path) -> dict[str, dict[str, Any]]:
    gold: dict[str, dict[str, Any]] = {}
    for row in load_jsonl(path):
        gold[str(row["id"])] = row
    if len(gold) != EXPECTED_CASE_COUNT:
        raise ValueError(
            f"expected {EXPECTED_CASE_COUNT} gold rows in {path.name}, got {len(gold)}"
        )
    return gold


def load_call_records(run_id: str) -> list[CallRecord]:
    path = Path("runs") / f"{run_id}.jsonl"
    if not path.exists():
        return []
    records: list[CallRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(CallRecord.model_validate_json(line))
    return records


def run_version(
    adapter: OllamaAdapter,
    run_id: str,
    cases: Sequence[dict[str, Any]],
    spec: PromptVersion,
    model_name: str,
    max_repairs: int,
    outputs_path: Path,
) -> list[OutputRecord]:
    template = load(PROMPT_ID, spec.version)
    schema_text = schema_description(spec.schema)
    system = substitute(template.system, {"schema_description": schema_text})
    records: list[OutputRecord] = []
    for case in cases:
        case_id = str(case["id"])
        source = str(case["source"])
        user_content = render_user(template, {}, untrusted=source)
        request = CompletionRequest(
            task="triage",
            case_id=case_id,
            prompt_id=PROMPT_ID,
            prompt_version=spec.version,
            system=system,
            user_content=user_content,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        trace = StructuredCallTrace()
        try:
            validated = complete_structured(
                adapter,
                request,
                spec.schema,
                run_id,
                max_repairs=max_repairs,
                trace=trace,
            )
            record = OutputRecord(
                run_id=run_id,
                task="triage",
                case_id=case_id,
                model_name=model_name,
                model_id=adapter.model_id,
                prompt_version=spec.version,
                succeeded=True,
                repairs=trace.repairs,
                output=validated.model_dump(),
                error=None,
            )
        except StructuredCompletionError as exc:
            record = OutputRecord(
                run_id=run_id,
                task="triage",
                case_id=case_id,
                model_name=model_name,
                model_id=adapter.model_id,
                prompt_version=spec.version,
                succeeded=False,
                repairs=exc.trace.repairs,
                output=None,
                error=str(exc),
            )
        for call in trace.records:
            append_call_record(call, run_id)
        append_output_record(outputs_path, record)
        records.append(record)
        print(
            f"triage {spec.version} {case_id} "
            f"succeeded={record.succeeded} repairs={record.repairs}"
        )
    return records


def score_records(
    outputs: Sequence[OutputRecord],
    gold_by_id: Mapping[str, Mapping[str, Any]],
) -> list[ScoreRecord]:
    scores: list[ScoreRecord] = []
    for record in outputs:
        gold = gold_by_id[record.case_id]
        scores.extend(
            score_case(
                run_id=record.run_id,
                case_id=record.case_id,
                model_name=record.model_name,
                prompt_version=record.prompt_version,
                output=record.output,
                expected_queue=str(gold["expected_queue"]),
                expected_escalation=bool(gold["expected_escalation"]),
            )
        )
    return scores


def _metric_total(
    scores: Sequence[ScoreRecord], prompt_version: str, metric: str
) -> tuple[int, int]:
    rows = [
        score
        for score in scores
        if score.prompt_version == prompt_version and score.metric == metric
    ]
    return sum(score.numerator for score in rows), sum(score.denominator for score in rows)


def _outputs_for(outputs: Sequence[OutputRecord], version: str) -> list[OutputRecord]:
    return [record for record in outputs if record.prompt_version == version]


def _queue_of(record: OutputRecord) -> str | None:
    if record.output is None:
        return None
    queue = record.output.get("queue")
    return str(queue) if queue is not None else None


def changed_queue_count(outputs: Sequence[OutputRecord]) -> int:
    v1 = {record.case_id: _queue_of(record) for record in _outputs_for(outputs, "v1")}
    v2 = {record.case_id: _queue_of(record) for record in _outputs_for(outputs, "v2")}
    return sum(1 for case_id, queue in v1.items() if v2.get(case_id) != queue)


def _tokens_per_case(calls: Sequence[CallRecord], version: str) -> float:
    totals: dict[str, int] = defaultdict(int)
    for call in calls:
        if call.prompt_version == version:
            totals[call.case_id] += call.output_tokens
    if not totals:
        return 0.0
    return sum(totals.values()) / len(totals)


def _case_latencies_ms(calls: Sequence[CallRecord], version: str) -> list[int]:
    totals: dict[str, int] = defaultdict(int)
    for call in calls:
        if call.prompt_version == version:
            totals[call.case_id] += call.latency_ms
    return list(totals.values())


def _median(values: Sequence[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _ms_to_seconds(value_ms: float) -> float:
    return value_ms / 1000.0


def render_notes(
    *,
    model_id: str,
    run_id: str,
    outputs: Sequence[OutputRecord],
    scores: Sequence[ScoreRecord],
    calls: Sequence[CallRecord],
) -> str:
    def line_for(version: str) -> str:
        queue_n, queue_d = _metric_total(scores, version, METRIC_QUEUE)
        esc_n, esc_d = _metric_total(scores, version, METRIC_ESCALATION)
        missed, _ = _metric_total(scores, version, METRIC_MISSED_ESCALATION)
        unnecessary, _ = _metric_total(scores, version, METRIC_UNNECESSARY_ESCALATION)
        boundary_n, boundary_d = _metric_total(scores, version, METRIC_HUMAN_BOUNDARY)
        return (
            f"triage.{version}: queue {queue_n}/{queue_d}, "
            f"escalation {esc_n}/{esc_d}, missed {missed}, "
            f"unnecessary {unnecessary}, boundary {boundary_n}/{boundary_d}"
        )

    v1_tokens = _tokens_per_case(calls, "v1")
    v2_tokens = _tokens_per_case(calls, "v2")
    delta = v2_tokens - v1_tokens
    v1_latencies = _case_latencies_ms(calls, "v1")
    v2_latencies = _case_latencies_ms(calls, "v2")
    v1_obs = sum(1 for call in calls if call.prompt_version == "v1")
    v2_obs = sum(1 for call in calls if call.prompt_version == "v2")
    changed = changed_queue_count(outputs)

    queue_v1, _ = _metric_total(scores, "v1", METRIC_QUEUE)
    queue_v2, _ = _metric_total(scores, "v2", METRIC_QUEUE)
    queue_delta = queue_v2 - queue_v1
    if delta <= 0 and queue_delta >= 0:
        conclusion = (
            "v2 did not spend extra output tokens, so the analysis field did not "
            "create a token cost on this 12-case run."
        )
    elif queue_delta == 0:
        conclusion = (
            "v2 spent extra output tokens without changing queue accuracy on this "
            "12-case set, so the analysis field did not earn its overhead."
        )
    elif abs(queue_delta) <= 1:
        conclusion = (
            "v2 spent extra output tokens and queue accuracy moved by one case; "
            "a one-case difference on 12 cases is a shrug, not a verdict, so the "
            "analysis field did not earn its overhead."
        )
    elif queue_delta > 1:
        conclusion = (
            "v2 improved queue routing by more than one case, which is the only "
            "result in this set that could justify the extra analysis tokens."
        )
    else:
        conclusion = (
            "v2 spent extra tokens and routed worse than v1, so the analysis field "
            "did not earn its overhead."
        )

    lines = [
        "# Day 4 notes: triage prompt comparison",
        "",
        (
            f"Model: {model_id} (logical name {LOGICAL_MODEL_KEY}), temperature "
            f"{TEMPERATURE}, run_id {run_id}. Both prompt versions ran all "
            f"{EXPECTED_CASE_COUNT} triage cases through complete_structured. "
            "provider/API cost = $0.00; token and latency overhead are measured "
            "from local Ollama call records."
        ),
        "",
        line_for("v1"),
        line_for("v2"),
        f"changed queue between versions: {changed}",
        (
            f"output tokens/case: v1 = {v1_tokens:.1f}, v2 = {v2_tokens:.1f}, "
            f"delta = {delta:+.1f}"
        ),
        (
            f"median latency: v1 = {_ms_to_seconds(_median(v1_latencies)):.2f}s, "
            f"v2 = {_ms_to_seconds(_median(v2_latencies)):.2f}s"
        ),
        (
            "maximum latency: v1 = "
            f"{_ms_to_seconds(max(v1_latencies) if v1_latencies else 0):.2f}s, "
            f"v2 = {_ms_to_seconds(max(v2_latencies) if v2_latencies else 0):.2f}s"
        ),
        f"observation count: v1 = {v1_obs}, v2 = {v2_obs}",
        f"conclusion: {conclusion}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    settings = Settings.from_env()
    run_id = str(uuid4())
    model_name = settings.models[LOGICAL_MODEL_KEY].logical_name
    model_id = settings.models[LOGICAL_MODEL_KEY].model_id
    adapter = OllamaAdapter(model_id=model_id)

    cases = load_cases(CASES_PATH)
    gold = load_gold(GOLD_PATH)

    outputs_path = RUNS_DIR / f"{run_id}.outputs.jsonl"
    outputs_path.parent.mkdir(parents=True, exist_ok=True)

    outputs: list[OutputRecord] = []
    for spec in PROMPT_VERSIONS:
        outputs.extend(
            run_version(
                adapter,
                run_id,
                cases,
                spec,
                model_name,
                settings.max_schema_repairs,
                outputs_path,
            )
        )

    scores = score_records(outputs, gold)
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(outputs_path, EVIDENCE_PATH)
    if SCORES_PATH.exists():
        SCORES_PATH.unlink()
    for score in scores:
        append_output_record(SCORES_PATH, score)

    calls = load_call_records(run_id)
    NOTES_PATH.write_text(
        render_notes(
            model_id=model_id,
            run_id=run_id,
            outputs=outputs,
            scores=scores,
            calls=calls,
        ),
        encoding="utf-8",
    )

    print(f"run_id={run_id}")
    print(f"call_records={Path('runs') / (run_id + '.jsonl')}")
    print(f"outputs={outputs_path}")
    print(f"evidence={EVIDENCE_PATH}")
    print(f"scores={SCORES_PATH}")
    print(f"notes={NOTES_PATH}")


if __name__ == "__main__":
    main()
