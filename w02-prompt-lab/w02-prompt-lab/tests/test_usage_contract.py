from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import get_args

import pytest

from promptlab.config import Settings
from promptlab.errors import UnknownModelError
from promptlab.usage import CallRecord, append_record, compute_cost

EXPECTED_FIELDS = {
    "record_id",
    "run_id",
    "timestamp",
    "provider",
    "model_id",
    "task",
    "case_id",
    "prompt_id",
    "prompt_version",
    "attempt",
    "temperature",
    "max_output_tokens",
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "latency_ms",
    "cost_usd",
    "stop_reason",
    "error_type",
    "response_text",
}


def make_record() -> CallRecord:
    model_id = Settings.from_env().models["mistral"].model_id
    return CallRecord(
        record_id="00000000-0000-4000-8000-000000000001",
        run_id="contract-test",
        timestamp=datetime.now(UTC),
        provider="ollama",
        model_id=model_id,
        task="extraction",
        case_id="E12",
        prompt_id="baseline",
        prompt_version="v0",
        attempt=1,
        temperature=0.0,
        max_output_tokens=256,
        input_tokens=100,
        output_tokens=20,
        cached_input_tokens=None,
        latency_ms=250,
        cost_usd=0.0,
        stop_reason="stop",
        error_type=None,
        response_text="example",
    )


def test_call_record_has_exact_fields() -> None:
    assert set(CallRecord.model_fields) == EXPECTED_FIELDS


def test_local_provider_and_task_literals_are_pinned() -> None:
    provider_annotation = CallRecord.model_fields["provider"].annotation
    task_annotation = CallRecord.model_fields["task"].annotation

    assert set(get_args(provider_annotation)) == {"ollama"}
    assert set(get_args(task_annotation)) == {"triage", "summarization", "extraction"}


def test_timestamp_must_be_timezone_aware() -> None:
    record = make_record()
    assert record.timestamp.tzinfo is not None
    assert record.timestamp.utcoffset() is not None


def test_known_local_model_has_zero_provider_charge() -> None:
    model_id = Settings.from_env().models["mistral"].model_id
    assert compute_cost(model_id, input_tokens=1234, output_tokens=567) == pytest.approx(0.0)


def test_unknown_model_raises() -> None:
    with pytest.raises(UnknownModelError):
        compute_cost("not-a-configured-model", input_tokens=10, output_tokens=10)


def test_append_record_appends_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    record = make_record()

    append_record(record, "contract-test")
    append_record(record, "contract-test")

    path = tmp_path / "runs" / "contract-test.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["case_id"] == "E12"
    assert json.loads(lines[1])["case_id"] == "E12"
