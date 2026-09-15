"""Offline tests for the bounded structured-output repair path."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.structured import StructuredCallTrace, StructuredCompletionError, complete_structured
from promptlab.usage import CallRecord


class Answer(BaseModel):
    value: str


class ScriptedAdapter:
    provider = "ollama"
    model_id = "fixture-model"

    def __init__(self, responses: list[CompletionResult]) -> None:
        self.responses = list(responses)
        self.requests: list[CompletionRequest] = []
        self.run_ids: list[str] = []

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        self.requests.append(request)
        self.run_ids.append(run_id)
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        return self.responses[index]


def _record(
    attempt: int,
    response_text: str | None,
    error_type: str | None,
) -> CallRecord:
    return CallRecord(
        record_id=f"record-{attempt}",
        run_id="fixture-run",
        timestamp=datetime.now(UTC),
        provider="ollama",
        model_id="fixture-model",
        task="summarization",
        case_id="S00",
        prompt_id="summarize",
        prompt_version="v1",
        attempt=attempt,
        temperature=0.0,
        max_output_tokens=128,
        input_tokens=12,
        output_tokens=20,
        cached_input_tokens=None,
        latency_ms=7,
        cost_usd=0.0,
        stop_reason=None if error_type else "stop",
        error_type=error_type,
        response_text=response_text,
    )


def _result(
    text: str | None,
    *,
    attempt: int = 1,
    error_type: str | None = None,
) -> CompletionResult:
    return CompletionResult(
        succeeded=text is not None,
        text=text,
        error_type=error_type,
        records=[_record(attempt, text, error_type)],
    )


def _request() -> CompletionRequest:
    return CompletionRequest(
        task="summarization",
        case_id="S00",
        prompt_id="summarize",
        prompt_version="v1",
        system="",
        user_content="Summarize the supplied procedure. DOCUMENT: ... END DOCUMENT.",
        temperature=0.0,
        max_output_tokens=128,
    )


def test_first_pass_valid_json_returns_object_with_zero_repairs() -> None:
    adapter = ScriptedAdapter([_result('{"value": "ok"}')])
    trace = StructuredCallTrace()

    result = complete_structured(adapter, _request(), Answer, "fixture-run", trace=trace)

    assert result == Answer(value="ok")
    assert len(adapter.requests) == 1
    assert adapter.run_ids == ["fixture-run"]
    assert trace.repairs == 0
    assert trace.first_error is None
    assert trace.final_error is None
    assert len(trace.records) == 1


def test_unparseable_text_is_repaired_once() -> None:
    original_content = _request().user_content
    adapter = ScriptedAdapter(
        [_result("no json here at all"), _result('{"value": "fixed"}', attempt=2)]
    )
    trace = StructuredCallTrace()

    result = complete_structured(
        adapter, _request(), Answer, "fixture-run", max_repairs=1, trace=trace
    )

    assert result == Answer(value="fixed")
    assert len(adapter.requests) == 2
    assert trace.repairs == 1
    assert trace.final_error is None

    repair_content = adapter.requests[1].user_content
    assert repair_content.startswith(original_content)
    assert "no json here at all" in repair_content
    assert "validation" in repair_content.lower()
    original = adapter.requests[0]
    assert adapter.requests[1].task == original.task
    assert adapter.requests[1].case_id == original.case_id
    assert adapter.requests[1].temperature == original.temperature
    assert adapter.requests[1].max_output_tokens == original.max_output_tokens


def test_wrong_shape_json_triggers_one_repair_naming_the_field() -> None:
    adapter = ScriptedAdapter(
        [_result('{"wrong": "shape"}'), _result('{"value": "fixed"}', attempt=2)]
    )
    trace = StructuredCallTrace()

    result = complete_structured(
        adapter, _request(), Answer, "fixture-run", max_repairs=1, trace=trace
    )

    assert result == Answer(value="fixed")
    assert trace.repairs == 1
    assert trace.first_error is not None and "value" in trace.first_error

    repair_content = adapter.requests[1].user_content
    assert '{"wrong": "shape"}' in repair_content
    assert "value" in repair_content
    assert "field required" in repair_content.lower()
    assert "validation error" in repair_content.lower()


def test_persistent_invalidity_raises_after_exactly_two_calls() -> None:
    adapter = ScriptedAdapter(
        [_result('{"wrong": "shape"}'), _result('{"still": "wrong"}', attempt=2)]
    )
    trace = StructuredCallTrace()

    with pytest.raises(StructuredCompletionError) as excinfo:
        complete_structured(adapter, _request(), Answer, "fixture-run", max_repairs=1, trace=trace)

    assert len(adapter.requests) == 2
    assert trace.repairs == 1
    assert trace.final_error is not None and "value" in trace.final_error
    assert excinfo.value.trace is trace


def test_max_repairs_zero_raises_after_one_call() -> None:
    adapter = ScriptedAdapter([_result("not json at all")])
    trace = StructuredCallTrace()

    with pytest.raises(StructuredCompletionError):
        complete_structured(adapter, _request(), Answer, "fixture-run", max_repairs=0, trace=trace)

    assert len(adapter.requests) == 1
    assert trace.repairs == 0
    assert trace.first_error is not None
    assert trace.final_error is not None


def test_transport_failure_raises_without_repair_call() -> None:
    adapter = ScriptedAdapter([_result(None, error_type="connection_error")])
    trace = StructuredCallTrace()

    with pytest.raises(StructuredCompletionError):
        complete_structured(adapter, _request(), Answer, "fixture-run", max_repairs=1, trace=trace)

    assert len(adapter.requests) == 1
    assert trace.repairs == 0
    assert trace.final_error is not None and "connection_error" in trace.final_error


def test_fenced_response_parses_with_zero_repairs() -> None:
    adapter = ScriptedAdapter([_result('```json\n{"value": "fenced"}\n```')])

    result = complete_structured(adapter, _request(), Answer, "fixture-run")

    assert result == Answer(value="fenced")
    assert len(adapter.requests) == 1


def test_trace_records_accumulate_across_calls_in_order() -> None:
    adapter = ScriptedAdapter(
        [_result('{"wrong": "shape"}'), _result('{"value": "fixed"}', attempt=2)]
    )
    trace = StructuredCallTrace()

    complete_structured(adapter, _request(), Answer, "fixture-run", max_repairs=1, trace=trace)

    assert [record.attempt for record in trace.records] == [1, 2]
    assert [record.response_text for record in trace.records] == [
        '{"wrong": "shape"}',
        '{"value": "fixed"}',
    ]
