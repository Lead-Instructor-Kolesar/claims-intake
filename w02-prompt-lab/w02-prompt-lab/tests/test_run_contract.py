from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.config import Settings
from promptlab.records import ScoreRecord, load_records
from promptlab.run import (
    TASK_ORDER,
    TASK_SPECS,
    build_parser,
    evaluate,
    planned_evaluations,
)
from promptlab.usage import CallRecord, compute_cost

RUN_PY = Path(__file__).resolve().parents[1] / "src" / "promptlab" / "run.py"

ABSENT = {"value": None, "status": "absent", "citation": None}


class StubAdapter:
    provider = "ollama"

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        text = json.dumps(_stub_output(request.task))
        record = CallRecord(
            record_id=str(uuid.uuid4()),
            run_id=run_id,
            timestamp=datetime.now(UTC),
            provider="ollama",
            model_id=self.model_id,
            task=request.task,
            case_id=request.case_id,
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            attempt=1,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            input_tokens=1,
            output_tokens=1,
            cached_input_tokens=None,
            latency_ms=1,
            cost_usd=compute_cost(self.model_id, 1, 1),
            stop_reason="stop",
            error_type=None,
            response_text=text,
        )
        return CompletionResult(
            succeeded=True,
            text=text,
            error_type=None,
            records=[record],
        )


def _stub_output(task: str) -> dict[str, object]:
    if task == "triage":
        return {
            "queue": "card_dispute",
            "escalation_required": False,
            "confidence": 0.5,
            "rationale": "stub",
            "draft_reply": "A specialist will review this.",
            "human_review_required": True,
            "customer_outcome": None,
        }
    if task == "summarization":
        return {
            "document_status": "unsupported",
            "title": ABSENT,
            "version": ABSENT,
            "effective_date": ABSENT,
            "purpose": ABSENT,
            "required_steps": ABSENT,
            "exceptions": ABSENT,
        }
    return {
        "document_status": "unsupported",
        "policy_name": ABSENT,
        "version": ABSENT,
        "effective_date": ABSENT,
        "jurisdictions": ABSENT,
        "beneficial_ownership_threshold": ABSENT,
        "review_frequency": ABSENT,
        "required_documents": ABSENT,
    }


def test_run_module_has_no_model_id_literals() -> None:
    source = RUN_PY.read_text(encoding="utf-8")
    assert "mistral:7b" not in source
    assert "qwen3:8b" not in source
    assert "httpx" not in source
    assert "11434" not in source


def test_locked_prompt_versions() -> None:
    assert TASK_SPECS["summarization"].prompt_id == "summarize"
    assert TASK_SPECS["summarization"].prompt_version == "v1"
    assert TASK_SPECS["extraction"].prompt_id == "extract"
    assert TASK_SPECS["extraction"].prompt_version == "v2"
    assert TASK_SPECS["triage"].prompt_id == "triage"
    assert TASK_SPECS["triage"].prompt_version == "v1"


def test_parser_requires_run_id() -> None:
    parser = build_parser(Settings.from_env())
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_default_plan_is_three_tasks_and_both_models() -> None:
    settings = Settings.from_env()
    assert planned_evaluations(TASK_ORDER, list(settings.models), None) == 72


def test_stub_run_writes_joinable_call_and_score_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env()
    model_name = next(iter(settings.models))
    run_id = "stub-day5"
    score_path = tmp_path / "scores.jsonl"
    run_docs = tmp_path / "day5-run.jsonl"

    evaluate(
        run_id=run_id,
        tasks=["extraction"],
        model_names=[model_name],
        settings=settings,
        adapter_factory=lambda model_id: StubAdapter(model_id),
        limit=2,
        score_path=score_path,
        run_docs_path=run_docs,
    )

    calls = [
        CallRecord.model_validate(json.loads(line))
        for line in run_docs.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    scores = load_records(score_path, ScoreRecord)
    assert len(calls) == 2
    assert {call.case_id for call in calls} == {"E01", "E02"}
    assert {call.run_id for call in calls} == {run_id}
    assert all(call.provider == "ollama" for call in calls)
    assert all(call.prompt_id == "extract" for call in calls)
    assert all(call.prompt_version == "v2" for call in calls)

    call_keys = {
        (call.run_id, call.case_id, call.task, call.model_id, call.prompt_id, call.prompt_version)
        for call in calls
    }
    for score in scores:
        key = (
            score.run_id,
            score.case_id,
            score.task,
            score.model_id,
            score.prompt_id,
            score.prompt_version,
        )
        assert key in call_keys
        assert score.scorer_version == "day5.v1"

    assert any(score.metric == "version_selection" for score in scores)
