from __future__ import annotations

from typing import get_args

import httpx
import pytest

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import Settings
from promptlab.errors import (
    PermanentProviderError,
    TransientProviderError,
    TruncatedResponseError,
)
from promptlab.usage import CallRecord


def _model_id(name: str) -> str:
    return Settings.from_env().models[name].model_id


def _request() -> CompletionRequest:
    return CompletionRequest(
        task="summarization",
        case_id="case_001",
        prompt_id="baseline",
        prompt_version="v0",
        system="You are a helpful assistant.",
        user_content="Summarize this procedure.",
        temperature=0.0,
        max_output_tokens=64,
    )


class StubAdapter:
    """Small network-free adapter used to prove the shared interface."""

    provider = "ollama"
    model_id = "fixture-model"

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        return CompletionResult(
            succeeded=True,
            text="ok",
            error_type=None,
            records=[],
        )


def accepts_adapter(adapter: ModelAdapter) -> CompletionResult:
    return adapter.complete(_request(), "fixture-run")


def test_stub_satisfies_model_adapter_contract() -> None:
    result = accepts_adapter(StubAdapter())

    assert result.succeeded is True
    assert result.text == "ok"
    assert result.error_type is None
    assert result.records == []


def test_completion_request_contract_is_exact() -> None:
    assert set(CompletionRequest.model_fields) == {
        "task",
        "case_id",
        "prompt_id",
        "prompt_version",
        "system",
        "user_content",
        "temperature",
        "max_output_tokens",
    }

    task_annotation = CompletionRequest.model_fields["task"].annotation
    assert set(get_args(task_annotation)) == {
        "triage",
        "summarization",
        "extraction",
    }


def test_completion_result_contract_is_exact() -> None:
    assert set(CompletionResult.model_fields) == {
        "succeeded",
        "text",
        "error_type",
        "records",
    }

    assert "CallRecord" in str(CompletionResult.model_fields["records"].annotation)
    assert CallRecord is not None


def test_same_ollama_adapter_class_can_target_both_models() -> None:
    mistral = OllamaAdapter(model_id=_model_id("mistral"))
    qwen = OllamaAdapter(model_id=_model_id("qwen"))

    assert type(mistral) is type(qwen)
    assert mistral.provider == "ollama"
    assert qwen.provider == "ollama"
    assert mistral.model_id != qwen.model_id


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "ok",
        prompt_tokens: int = 11,
        output_tokens: int = 4,
        done_reason: str = "stop",
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = {
            # Include both common Ollama response shapes so the contract does
            # not force students to use /api/chat instead of /api/generate.
            "message": {"content": text},
            "response": text,
            "prompt_eval_count": prompt_tokens,
            "eval_count": output_tokens,
            "done_reason": done_reason,
        }

    def json(self) -> dict[str, object]:
        return self._payload


def test_success_maps_ollama_usage_into_call_record(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    calls = 0

    def fake_post(*args, **kwargs) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse(
            text="summary",
            prompt_tokens=123,
            output_tokens=17,
            done_reason="stop",
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    adapter = OllamaAdapter(model_id=_model_id("mistral"))
    result = adapter.complete(_request(), "success-run")

    assert calls == 1
    assert result.succeeded is True
    assert result.error_type is None
    assert len(result.records) == 1

    record = result.records[0]
    assert record.provider == "ollama"
    assert record.model_id == _model_id("mistral")
    assert record.input_tokens == 123
    assert record.output_tokens == 17
    assert record.stop_reason == "stop"
    assert record.attempt == 1
    assert record.cost_usd == pytest.approx(0.0)


def test_transient_failure_retries_and_records_each_attempt(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)

    calls = 0

    def flaky_post(*args, **kwargs) -> FakeResponse:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("temporary connection failure")
        return FakeResponse(text="eventual success")

    monkeypatch.setattr(httpx, "post", flaky_post)
    monkeypatch.setattr("time.sleep", lambda _: None)

    adapter = OllamaAdapter(model_id=_model_id("mistral"))
    result = adapter.complete(_request(), "retry-run")

    assert calls == 3
    assert result.succeeded is True
    assert [record.attempt for record in result.records] == [1, 2, 3]
    assert result.records[0].error_type == TransientProviderError.__name__
    assert result.records[1].error_type == TransientProviderError.__name__
    assert result.records[2].error_type is None


def test_permanent_failure_is_not_retried(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    calls = 0

    def bad_request(*args, **kwargs) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse(status_code=400, text="bad request")

    monkeypatch.setattr(httpx, "post", bad_request)

    adapter = OllamaAdapter(model_id=_model_id("mistral"))
    result = adapter.complete(_request(), "permanent-run")

    assert calls == 1
    assert result.succeeded is False
    assert result.error_type == PermanentProviderError.__name__
    assert len(result.records) == 1
    assert result.records[0].attempt == 1
    assert result.records[0].error_type == PermanentProviderError.__name__


def test_truncation_is_recorded_and_not_retried(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    calls = 0

    def truncated(*args, **kwargs) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse(
            text="partial output",
            prompt_tokens=40,
            output_tokens=64,
            done_reason="length",
        )

    monkeypatch.setattr(httpx, "post", truncated)

    adapter = OllamaAdapter(model_id=_model_id("qwen"))
    result = adapter.complete(_request(), "truncation-run")

    assert calls == 1
    assert result.succeeded is False
    assert result.error_type == TruncatedResponseError.__name__
    assert len(result.records) == 1

    record = result.records[0]
    assert record.attempt == 1
    assert record.stop_reason == "length"
    assert record.error_type == TruncatedResponseError.__name__
