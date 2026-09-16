from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.config import MAX_OUTPUT_TOKENS, Settings
from promptlab.records import ScoreRecord, UsageRecord, load_records
from promptlab.run import RecordingAdapter, main, run_evaluation
from promptlab.usage import CallRecord


def _call(
    *,
    request: CompletionRequest,
    run_id: str,
    model_id: str,
    attempt: int,
    error_type: str | None,
    text: str | None,
) -> CallRecord:
    return CallRecord(
        record_id=str(uuid4()),
        run_id=run_id,
        timestamp=datetime.now(UTC),
        provider="ollama",
        model_id=model_id,
        task=request.task,
        case_id=request.case_id,
        prompt_id=request.prompt_id,
        prompt_version=request.prompt_version,
        attempt=attempt,
        temperature=request.temperature,
        max_output_tokens=request.max_output_tokens,
        input_tokens=10,
        output_tokens=20,
        cached_input_tokens=None,
        latency_ms=5,
        cost_usd=0.0,
        stop_reason=None if error_type is None else "error",
        error_type=error_type,
        response_text=text,
    )


class FakeAdapter:
    provider = "ollama"

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self._scripted: dict[str, list[CompletionResult]] = {}
        self._default_calls = 0

    def script(self, case_id: str, results: list[CompletionResult]) -> None:
        self._scripted[case_id] = list(results)

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        queued = self._scripted.get(request.case_id)
        if queued:
            return queued.pop(0)

        self._default_calls += 1
        text = _valid_payload(request.task)
        record = _call(
            request=request,
            run_id=run_id,
            model_id=self.model_id,
            attempt=1,
            error_type=None,
            text=text,
        )
        return CompletionResult(
            succeeded=True,
            text=text,
            error_type=None,
            records=[record],
        )


def _valid_payload(task: str) -> str:
    if task == "triage":
        return json.dumps(
            {
                "queue": "card_dispute",
                "escalation_required": False,
                "confidence": 0.9,
                "rationale": "Recognized merchant charge.",
                "draft_reply": "A specialist will review your request.",
                "human_review_required": True,
                "customer_outcome": None,
            }
        )
    if task == "summarization":
        field = {
            "value": None,
            "status": "absent",
            "citation": None,
        }
        present = {
            "value": "Example",
            "status": "present",
            "citation": "1. Document Control",
        }
        return json.dumps(
            {
                "document_status": "valid",
                "title": present,
                "version": present,
                "effective_date": present,
                "purpose": field,
                "required_steps": field,
                "exceptions": field,
            }
        )
    field = {"value": None, "status": "absent", "citation": None}
    present = {
        "value": "Example",
        "status": "present",
        "citation": "1. Document Control",
    }
    return json.dumps(
        {
            "document_status": "valid",
            "policy_name": present,
            "version": present,
            "effective_date": present,
            "jurisdictions": field,
            "beneficial_ownership_threshold": field,
            "review_frequency": field,
            "required_documents": field,
        }
    )


def test_run_py_has_no_httpx_or_model_literals() -> None:
    source = Path("src/promptlab/run.py").read_text(encoding="utf-8")
    assert "httpx" not in source
    assert "mistral:7b" not in source
    assert "qwen3:8b" not in source


def test_full_harness_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env()
    adapters: dict[str, FakeAdapter] = {
        model.model_id: FakeAdapter(model.model_id) for model in settings.models.values()
    }

    # Force one case through all usage kinds/statuses on mistral triage T01.
    mistral = settings.models["mistral"]
    adapters[mistral.model_id].script(
        "T01",
        [
            CompletionResult(
                succeeded=True,
                text="{not-json",
                error_type=None,
                records=[
                    _call(
                        request=CompletionRequest(
                            task="triage",
                            case_id="T01",
                            prompt_id="triage",
                            prompt_version="v1",
                            system="",
                            user_content="x",
                            temperature=0.0,
                            max_output_tokens=MAX_OUTPUT_TOKENS,
                        ),
                        run_id="day5-test",
                        model_id=mistral.model_id,
                        attempt=1,
                        error_type="TransientProviderError",
                        text=None,
                    ),
                    _call(
                        request=CompletionRequest(
                            task="triage",
                            case_id="T01",
                            prompt_id="triage",
                            prompt_version="v1",
                            system="",
                            user_content="x",
                            temperature=0.0,
                            max_output_tokens=MAX_OUTPUT_TOKENS,
                        ),
                        run_id="day5-test",
                        model_id=mistral.model_id,
                        attempt=2,
                        error_type=None,
                        text="{not-json",
                    ),
                ],
            ),
            CompletionResult(
                succeeded=True,
                text=_valid_payload("triage"),
                error_type=None,
                records=[
                    _call(
                        request=CompletionRequest(
                            task="triage",
                            case_id="T01",
                            prompt_id="triage",
                            prompt_version="v1",
                            system="",
                            user_content="x",
                            temperature=0.0,
                            max_output_tokens=MAX_OUTPUT_TOKENS,
                        ),
                        run_id="day5-test",
                        model_id=mistral.model_id,
                        attempt=1,
                        error_type="TransientProviderError",
                        text=None,
                    ),
                    _call(
                        request=CompletionRequest(
                            task="triage",
                            case_id="T01",
                            prompt_id="triage",
                            prompt_version="v1",
                            system="",
                            user_content="x",
                            temperature=0.0,
                            max_output_tokens=MAX_OUTPUT_TOKENS,
                        ),
                        run_id="day5-test",
                        model_id=mistral.model_id,
                        attempt=2,
                        error_type=None,
                        text=_valid_payload("triage"),
                    ),
                ],
            ),
        ],
    )

    def factory(model, _settings):  # type: ignore[no-untyped-def]
        return adapters[model.model_id]

    docs_run = tmp_path / "docs" / "day5-run.jsonl"
    docs_scores = tmp_path / "docs" / "day5-scores.jsonl"
    report = tmp_path / "reports" / "comparison.md"
    decision = tmp_path / "docs" / "model-decision.md"

    usage, outputs, scores = run_evaluation(
        run_id="day5-test",
        tasks=["triage", "summarization", "extraction"],
        model_names=["mistral", "qwen"],
        limit=None,
        settings=settings,
        adapter_factory=factory,
        docs_run_path=docs_run,
        docs_scores_path=docs_scores,
        report_path=report,
        decision_path=decision,
        runs_root=tmp_path / "runs",
    )

    assert len(outputs) == 72
    assert {row.run_id for row in outputs} == {"day5-test"}
    assert {row.run_id for row in usage} == {"day5-test"}
    assert {row.run_id for row in scores} == {"day5-test"}

    kinds = {row.kind for row in usage}
    statuses = {row.status for row in usage}
    assert kinds >= {"primary", "transport_retry", "repair", "repair_retry"}
    assert statuses >= {"success", "schema_invalid", "transport_error"}

    output_keys = {
        (row.run_id, row.task, row.case_id, row.model_name, row.prompt_version)
        for row in outputs
    }
    for score in scores:
        key = (
            score.run_id,
            score.task,
            score.case_id,
            score.model_name,
            score.prompt_version,
        )
        assert key in output_keys

    written_usage = load_records(tmp_path / "runs" / "day5-test" / "usage.jsonl", UsageRecord)
    written_scores = load_records(
        tmp_path / "runs" / "day5-test" / "scores.jsonl", ScoreRecord
    )
    assert written_usage
    assert written_scores
    assert docs_run.exists()
    assert docs_scores.exists()
    assert report.exists()
    assert decision.exists()


def test_cli_filters_task_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings.from_env()
    adapters = {
        model.model_id: FakeAdapter(model.model_id) for model in settings.models.values()
    }

    def factory(model, _settings):  # type: ignore[no-untyped-def]
        return adapters[model.model_id]

    usage, outputs, scores = run_evaluation(
        run_id="day5-filter",
        tasks=["triage"],
        model_names=["mistral"],
        limit=2,
        settings=settings,
        adapter_factory=factory,
        docs_run_path=tmp_path / "docs" / "day5-run.jsonl",
        docs_scores_path=tmp_path / "docs" / "day5-scores.jsonl",
        report_path=tmp_path / "reports" / "comparison.md",
        decision_path=tmp_path / "docs" / "model-decision.md",
        runs_root=tmp_path / "runs",
    )
    assert len(outputs) == 2
    assert {row.task for row in outputs} == {"triage"}
    assert {row.model_name for row in outputs} == {"mistral"}
    assert usage and scores


def test_validate_only(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--validate-only"])
    captured = capsys.readouterr().out
    assert "triage=12" in captured
    assert "summarization=12" in captured
    assert "extraction=12" in captured


def test_recording_adapter_counts_semantic_calls() -> None:
    inner = FakeAdapter("mistral:7b")
    adapter = RecordingAdapter(inner)
    request = CompletionRequest(
        task="triage",
        case_id="T01",
        prompt_id="triage",
        prompt_version="v1",
        system="",
        user_content="hi",
        temperature=0.0,
        max_output_tokens=32,
    )
    adapter.complete(request, "run")
    adapter.complete(request, "run")
    assert adapter.calls == 2
    assert len(adapter.records) == 2
