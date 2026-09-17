"""Day 5 runner: one command compares three tasks across both local models.

Runs the selected prompt version per task through the mandated chain
(registry -> complete_structured -> ModelAdapter -> OllamaAdapter), records
every attempt through the Day 1 usage contract, scores deterministically
against the gold labels, and generates the comparison report plus the model
decision scaffold. The experimental variables are the configured model_id
and the documented per-task prompt version; nothing else varies between
configurations.

Selected prompt versions (never edited after recording results):
- summarization -> summarize.v1
- extraction    -> extract.v2
- triage        -> triage.v2, the Day 4 analysis-first version, where the
  schema description lists analysis before the routing fields
"""

from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel

from promptlab.adapters.base import CompletionRequest
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import PROJECT_ROOT, Settings
from promptlab.corpus import Case, GoldLabel, load_cases, validate_corpus
from promptlab.prompts import PromptTemplate, load, render_user, substitute
from promptlab.records import OutputRecord, ScoreRecord, UsageRecord
from promptlab.records import append_record as append_output_record
from promptlab.report import write_reports
from promptlab.rules import VersionCandidate, select_current_version
from promptlab.schemas import (
    PolicyExtraction,
    SummarizationOutput,
    TaskName,
    TriageOutputWithAnalysis,
    schema_description,
)
from promptlab.scoring import (
    score_case,
    score_evidence_case,
    score_pii_case,
    score_version_selection,
)
from promptlab.structured import (
    StructuredCallTrace,
    StructuredCompletionError,
    complete_structured,
)
from promptlab.usage import CallRecord
from promptlab.usage import append_record as append_call_record

EXPECTED_CASE_COUNT = 12
MAX_OUTPUT_TOKENS = 1024

RUNS_DIR = PROJECT_ROOT / "runs"
RUN_OUTPUTS_PATH = PROJECT_ROOT / "docs" / "day5-run.jsonl"
SCORES_PATH = PROJECT_ROOT / "docs" / "day5-scores.jsonl"
REPORT_PATH = PROJECT_ROOT / "reports" / "comparison.md"
DECISION_PATH = PROJECT_ROOT / "docs" / "model-decision.md"

EVIDENCE_TASKS: tuple[TaskName, ...] = ("summarization", "extraction")


@dataclass(frozen=True)
class TaskSpec:
    """The measured prompt configuration for one task."""

    task: TaskName
    prompt_id: str
    prompt_version: str
    schema: type[BaseModel]
    selection_reason: str


TASK_SPECS: dict[TaskName, TaskSpec] = {
    "summarization": TaskSpec(
        task="summarization",
        prompt_id="summarize",
        prompt_version="v1",
        schema=SummarizationOutput,
        selection_reason="the Day 3 measured version",
    ),
    "extraction": TaskSpec(
        task="extraction",
        prompt_id="extract",
        prompt_version="v2",
        schema=PolicyExtraction,
        selection_reason="the Day 3 few-shot version",
    ),
    "triage": TaskSpec(
        task="triage",
        prompt_id="triage",
        prompt_version="v2",
        schema=TriageOutputWithAnalysis,
        selection_reason=(
            "the Day 4 analysis-first version: the schema description lists "
            "analysis before the routing fields, so the field is generated "
            "before the queue is chosen"
        ),
    ),
}


def _load_task_pairs(
    task: TaskName, limit: int | None
) -> list[tuple[Case, GoldLabel]]:
    pairs = load_cases(task)
    if len(pairs) != EXPECTED_CASE_COUNT:
        raise ValueError(
            f"expected {EXPECTED_CASE_COUNT} {task} cases, got {len(pairs)}"
        )
    if limit is not None:
        pairs = pairs[:limit]
    return pairs


def _request_for(
    *,
    template: PromptTemplate,
    spec: TaskSpec,
    case: Case,
    temperature: float,
) -> CompletionRequest:
    schema_text = schema_description(spec.schema)
    # Day 3 prompts carry the schema description in the user layer and have an
    # empty system layer; day 4 triage prompts carry it in the system layer.
    # substitute() ignores names a layer does not use, so supply it to both.
    system = substitute(template.system, {"schema_description": schema_text})
    user_content = render_user(
        template, {"schema_description": schema_text}, untrusted=case.document_text
    )
    return CompletionRequest(
        task=spec.task,
        case_id=case.id,
        prompt_id=spec.prompt_id,
        prompt_version=spec.prompt_version,
        system=system,
        user_content=user_content,
        temperature=temperature,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def run_task_model(
    *,
    adapter: OllamaAdapter,
    run_id: str,
    spec: TaskSpec,
    template: PromptTemplate,
    pairs: list[tuple[Case, GoldLabel]],
    model_name: str,
    temperature: float,
    max_repairs: int,
    repair_record_ids: set[str],
    outputs_path: Path,
) -> list[OutputRecord]:
    """Run one task/model configuration, recording every attempt."""
    records: list[OutputRecord] = []
    for case, _gold in pairs:
        request = _request_for(
            template=template, spec=spec, case=case, temperature=temperature
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
                task=spec.task,
                case_id=case.id,
                model_name=model_name,
                model_id=adapter.model_id,
                prompt_id=spec.prompt_id,
                prompt_version=spec.prompt_version,
                succeeded=True,
                repairs=trace.repairs,
                output=validated.model_dump(),
                error=None,
            )
        except StructuredCompletionError as exc:
            record = OutputRecord(
                run_id=run_id,
                task=spec.task,
                case_id=case.id,
                model_name=model_name,
                model_id=adapter.model_id,
                prompt_id=spec.prompt_id,
                prompt_version=spec.prompt_version,
                succeeded=False,
                repairs=exc.trace.repairs,
                output=None,
                error=str(exc),
            )
        repair_record_ids.update(trace.repair_record_ids)
        for call in trace.records:
            append_call_record(call, run_id)
        append_output_record(outputs_path, record)
        records.append(record)
        print(
            f"{spec.task} {spec.prompt_version} {model_name} {case.id} "
            f"succeeded={record.succeeded} repairs={record.repairs}"
        )
    return records


def _evidence_fields_of(output: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(name): value
        for name, value in output.items()
        if isinstance(value, Mapping) and "status" in value
    }


def _free_texts_of(output: Mapping[str, Any]) -> list[str]:
    """Free-text output values the deterministic PII scan must inspect."""
    texts: list[str] = []
    for field in _evidence_fields_of(output).values():
        if field.get("status") != "present":
            continue
        value = field.get("value")
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, list):
            texts.extend(str(item) for item in value)
    return texts


def _triage_texts_of(output: Mapping[str, Any]) -> list[str]:
    texts = [
        str(output.get("draft_reply", "")),
        str(output.get("rationale", "")),
    ]
    analysis = output.get("analysis")
    if isinstance(analysis, str):
        texts.append(analysis)
    outcome = output.get("customer_outcome")
    if outcome is not None:
        texts.append(str(outcome))
    return texts


def _score_task_model(
    *,
    run_id: str,
    spec: TaskSpec,
    outputs: Sequence[OutputRecord],
    pairs: list[tuple[Case, GoldLabel]],
    source_by_id: Mapping[str, str],
) -> list[ScoreRecord]:
    """Deterministic per-case scoring for one task/model configuration."""
    scores: list[ScoreRecord] = []
    gold_by_id = {gold.id: gold for _case, gold in pairs}
    for record in outputs:
        gold = gold_by_id[record.case_id]
        output = record.output if record.succeeded else None
        if spec.task == "triage":
            scores.extend(
                score_case(
                    run_id=run_id,
                    case_id=record.case_id,
                    model_name=record.model_name,
                    prompt_version=record.prompt_version,
                    prompt_id=spec.prompt_id,
                    output=output,
                    expected_queue=str(gold.expected_queue),
                    expected_escalation=bool(gold.expected_escalation),
                )
            )
            texts = _triage_texts_of(output) if output is not None else []
        else:
            scores.extend(
                score_evidence_case(
                    run_id=run_id,
                    task=spec.task,
                    case_id=record.case_id,
                    model_name=record.model_name,
                    prompt_version=record.prompt_version,
                    prompt_id=spec.prompt_id,
                    source_text=source_by_id[record.case_id],
                    recoverable_fields=list(gold.recoverable_fields),
                    output=output,
                )
            )
            texts = _free_texts_of(output) if output is not None else []
        scores.append(
            score_pii_case(
                run_id=run_id,
                task=spec.task,
                case_id=record.case_id,
                model_name=record.model_name,
                prompt_version=record.prompt_version,
                prompt_id=spec.prompt_id,
                texts=texts,
            )
        )
    return scores


def _candidate_from_output(record: OutputRecord | None) -> VersionCandidate | None:
    """Convert one extraction output into a rule candidate, or skip it."""
    if record is None or not record.succeeded or record.output is None:
        return None
    fields = _evidence_fields_of(record.output)
    version_field = fields.get("version")
    date_field = fields.get("effective_date")
    if version_field is None or date_field is None:
        return None
    if version_field.get("status") != "present" or date_field.get("status") != "present":
        return None
    version_value = version_field.get("value")
    date_value = date_field.get("value")
    if not isinstance(version_value, str) or not isinstance(date_value, str):
        return None
    try:
        effective = date.fromisoformat(date_value.strip())
    except ValueError:
        return None
    return VersionCandidate(
        case_id=record.case_id, version=version_value.strip(), effective_date=effective
    )


def _version_selection_scores(
    *,
    run_id: str,
    spec: TaskSpec,
    model_name: str,
    outputs: Sequence[OutputRecord],
    pairs: list[tuple[Case, GoldLabel]],
) -> list[ScoreRecord]:
    """Score select_current_version verdicts per version group against gold.

    The rule decides currency deterministically; the model only supplies the
    version and effective-date evidence the rule consumes.
    """
    gold_by_id = {gold.id: gold for _case, gold in pairs}
    outputs_by_case = {record.case_id: record for record in outputs}

    members_by_group: dict[str, list[GoldLabel]] = defaultdict(list)
    for gold in gold_by_id.values():
        extra = gold.model_extra or {}
        group = extra.get("version_group")
        if group:
            members_by_group[str(group)].append(gold)

    scores: list[ScoreRecord] = []
    for group_name in sorted(members_by_group):
        members = members_by_group[group_name]
        first_extra = members[0].model_extra or {}
        as_of = date.fromisoformat(str(first_extra["as_of"]))
        expected = first_extra.get("expected_current_case_id")
        expected_id = str(expected) if expected is not None else None

        candidates: list[VersionCandidate] = []
        skipped: list[str] = []
        for gold in members:
            candidate = _candidate_from_output(outputs_by_case.get(gold.id))
            if candidate is None:
                skipped.append(gold.id)
            else:
                candidates.append(candidate)

        selected = select_current_version(candidates, as_of)
        detail = f"as_of={as_of.isoformat()} parsed={len(candidates)}/{len(members)}"
        if skipped:
            detail += f" unusable={','.join(skipped)}"
        if selected is None:
            detail += " rule returned None"

        scores.append(
            score_version_selection(
                run_id=run_id,
                task=spec.task,
                case_id=f"VG:{group_name}",
                model_name=model_name,
                prompt_version=spec.prompt_version,
                prompt_id=spec.prompt_id,
                selected_case_id=selected.case_id if selected else None,
                expected_case_id=expected_id,
                rule_detail=detail,
            )
        )
    return scores


def _usage_records(
    calls: Sequence[CallRecord],
    repair_record_ids: set[str],
    name_by_model_id: Mapping[str, str],
) -> list[UsageRecord]:
    """Project call records onto the reporting contract.

    Repair calls restart adapter attempt numbering, so the structured trace's
    repair record ids are the only reliable way to tell a semantic repair from
    a transport retry.
    """
    usage: list[UsageRecord] = []
    for call in calls:
        if call.record_id in repair_record_ids:
            kind: Literal["primary", "transport_retry", "repair", "repair_retry"] = (
                "repair"
            )
        elif call.attempt > 1:
            kind = "transport_retry"
        else:
            kind = "primary"
        usage.append(
            UsageRecord(
                run_id=call.run_id,
                task=call.task,
                case_id=call.case_id,
                model_name=name_by_model_id[call.model_id],
                model_id=call.model_id,
                prompt_id=call.prompt_id,
                prompt_version=call.prompt_version,
                attempt=call.attempt,
                kind=kind,
                status="transport_error" if call.error_type else "success",
                prompt_tokens=call.input_tokens,
                completion_tokens=call.output_tokens,
                latency_ms=float(call.latency_ms),
                cost_usd=Decimal(str(call.cost_usd)),
                error=call.error_type,
            )
        )
    return usage


def _load_call_records(run_id: str) -> list[CallRecord]:
    path = RUNS_DIR / f"{run_id}.jsonl"
    if not path.exists():
        return []
    records: list[CallRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(CallRecord.model_validate_json(line))
    return records


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Week 2 three-task local model comparison."
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Shared run id for the whole comparison (default: a new uuid4).",
    )
    parser.add_argument(
        "--task",
        action="append",
        choices=sorted(TASK_SPECS),
        help="Task to run; repeat for several. Default: all three.",
    )
    parser.add_argument(
        "--model",
        action="append",
        choices=["mistral", "qwen"],
        help="Configured logical model name; repeat for several. Default: both.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N cases per task (smoke runs).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Check corpus, gold, prompts, and schemas without model calls.",
    )
    return parser.parse_args()


def validate_only(task_names: Sequence[TaskName]) -> None:
    """Preflight every task without touching Ollama."""
    counts = validate_corpus()
    print(f"corpus counts: {counts}")
    for task in task_names:
        spec = TASK_SPECS[task]
        pairs = _load_task_pairs(task, limit=None)
        template = load(spec.prompt_id, spec.prompt_version)
        case, _gold = pairs[0]
        request = _request_for(
            template=template, spec=spec, case=case, temperature=0.0
        )
        if not request.user_content:
            raise ValueError(
                f"empty rendered user layer for {spec.prompt_id}.{spec.prompt_version}"
            )
        description = schema_description(spec.schema)
        grouped = sum(
            1
            for _case, gold in pairs
            if (gold.model_extra or {}).get("version_group")
        )
        print(
            f"{task}: cases={len(pairs)} "
            f"prompt={spec.prompt_id}.{spec.prompt_version} "
            f"schema={spec.schema.__name__} "
            f"description_lines={len(description.splitlines())} "
            f"grouped_cases={grouped}"
        )
    print("validate-only: no model calls were made")


def main() -> None:
    args = _parse_args()
    settings = Settings.from_env()
    task_names: list[TaskName] = list(args.task) if args.task else list(TASK_SPECS)
    model_names: list[str] = args.model or sorted(settings.models)

    if args.validate_only:
        validate_only(task_names)
        return

    run_id = args.run_id or str(uuid4())
    temperature = settings.temperature
    repair_record_ids: set[str] = set()

    outputs_path = RUNS_DIR / f"{run_id}.outputs.jsonl"
    outputs_path.parent.mkdir(parents=True, exist_ok=True)

    outputs: list[OutputRecord] = []
    for task in task_names:
        spec = TASK_SPECS[task]
        template = load(spec.prompt_id, spec.prompt_version)
        pairs = _load_task_pairs(task, limit=args.limit)
        for model_name in model_names:
            adapter = OllamaAdapter(model_id=settings.models[model_name].model_id)
            outputs.extend(
                run_task_model(
                    adapter=adapter,
                    run_id=run_id,
                    spec=spec,
                    template=template,
                    pairs=pairs,
                    model_name=model_name,
                    temperature=temperature,
                    max_repairs=settings.max_schema_repairs,
                    repair_record_ids=repair_record_ids,
                    outputs_path=outputs_path,
                )
            )

    scores: list[ScoreRecord] = []
    for task in task_names:
        spec = TASK_SPECS[task]
        pairs = _load_task_pairs(task, limit=args.limit)
        source_by_id = {case.id: case.document_text for case, _gold in pairs}
        task_outputs = [record for record in outputs if record.task == task]
        for model_name in model_names:
            model_outputs = [
                record for record in task_outputs if record.model_name == model_name
            ]
            if not model_outputs:
                continue
            scores.extend(
                _score_task_model(
                    run_id=run_id,
                    spec=spec,
                    outputs=model_outputs,
                    pairs=pairs,
                    source_by_id=source_by_id,
                )
            )
            if task in EVIDENCE_TASKS:
                scores.extend(
                    _version_selection_scores(
                        run_id=run_id,
                        spec=spec,
                        model_name=model_name,
                        outputs=model_outputs,
                        pairs=pairs,
                    )
                )

    RUN_OUTPUTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(outputs_path, RUN_OUTPUTS_PATH)
    if SCORES_PATH.exists():
        SCORES_PATH.unlink()
    for score in scores:
        append_output_record(SCORES_PATH, score)

    calls = _load_call_records(run_id)
    usage = _usage_records(
        calls,
        repair_record_ids,
        {config.model_id: logical for logical, config in settings.models.items()},
    )

    write_reports(
        run_id=run_id,
        models=model_names,
        usage=usage,
        outputs=outputs,
        scores=scores,
        report_path=REPORT_PATH,
        decision_path=DECISION_PATH,
    )

    succeeded = sum(1 for record in outputs if record.succeeded)
    print(f"run_id={run_id}")
    print(f"evaluations={len(outputs)} succeeded={succeeded} scores={len(scores)}")
    print(f"call_records={RUNS_DIR / (run_id + '.jsonl')}")
    print(f"run_outputs={RUN_OUTPUTS_PATH}")
    print(f"scores={SCORES_PATH}")
    print(f"report={REPORT_PATH}")
    print(f"decision={DECISION_PATH}")


if __name__ == "__main__":
    main()
