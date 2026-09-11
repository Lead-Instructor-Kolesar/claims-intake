from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import Settings
from promptlab.errors import (
    PermanentProviderError,
    TransientProviderError,
    TruncatedResponseError,
    UnknownModelError,
)
from promptlab.usage import CallRecord


def _provider(client: ModelAdapter) -> str:
    return client.provider


def configured_model_id() -> str:
    return Settings.from_env().models["mistral"].model_id


def request() -> CompletionRequest:
    return CompletionRequest(
        task="summarization",
        case_id="S01",
        prompt_id="baseline",
        prompt_version="v0",
        system="Follow the document.",
        user_content="summarize this",
        temperature=0.0,
        max_output_tokens=256,
    )


def payload(
    *,
    response: str = "summary",
    prompt_eval_count: int = 40,
    eval_count: int = 12,
    done_reason: str | None = "stop",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "response": response,
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
    }
    if done_reason is not None:
        body["done_reason"] = done_reason
    return body


def http_response(status: int, body: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        json=body if body is not None else {"error": "nope"},
        request=httpx.Request("POST", "http://ollama.test/api/generate"),
    )


def adapter() -> OllamaAdapter:
    return OllamaAdapter(model_id=configured_model_id(), base_url="http://ollama.test")


def test_contract_types_match_the_assignment() -> None:
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
    assert set(CompletionResult.model_fields) == {
        "succeeded",
        "text",
        "error_type",
        "records",
    }
    client: ModelAdapter = adapter()
    assert _provider(client) == "ollama"
    assert client.model_id == configured_model_id()
    assert issubclass(TransientProviderError, Exception)
    assert issubclass(PermanentProviderError, Exception)
    assert issubclass(TruncatedResponseError, Exception)
    assert issubclass(UnknownModelError, ValueError)


def test_success_maps_response_into_one_call_record(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["timeout"] = kwargs["timeout"]
        return http_response(200, payload(prompt_eval_count=111, eval_count=22))

    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", fake_post)
    result = adapter().complete(request(), "run-ok")

    assert captured["url"] == "http://ollama.test/api/generate"
    assert captured["timeout"] == 180.0
    assert captured["json"]["model"] == configured_model_id()
    assert captured["json"]["prompt"] == "summarize this"
    assert captured["json"]["system"] == "Follow the document."
    assert captured["json"]["stream"] is False
    assert captured["json"]["options"] == {"temperature": 0.0, "num_predict": 256}

    assert result.succeeded is True
    assert result.text == "summary"
    assert result.error_type is None
    assert len(result.records) == 1
    record = result.records[0]
    assert isinstance(record, CallRecord)
    assert record.provider == "ollama"
    assert record.model_id == configured_model_id()
    assert record.task == "summarization"
    assert record.case_id == "S01"
    assert record.prompt_id == "baseline"
    assert record.prompt_version == "v0"
    assert record.attempt == 1
    assert record.temperature == 0.0
    assert record.max_output_tokens == 256
    assert record.input_tokens == 111
    assert record.output_tokens == 22
    assert record.cached_input_tokens is None
    assert record.cost_usd == pytest.approx(0.0)
    assert record.stop_reason == "stop"
    assert record.error_type is None
    assert record.response_text == "summary"
    assert record.run_id == "run-ok"
    assert record.timestamp.tzinfo is not None
    assert record.timestamp.utcoffset() is not None


def test_truncation_is_recorded_and_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        nonlocal calls
        calls += 1
        return http_response(200, payload(response="cut", done_reason="length", eval_count=256))

    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", fake_post)
    sleeps: list[float] = []
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", sleeps.append)

    result = adapter().complete(request(), "run-trunc")

    assert calls == 1
    assert sleeps == []
    assert result.succeeded is False
    assert result.error_type == "TruncatedResponseError"
    assert result.text == "cut"
    assert len(result.records) == 1
    assert result.records[0].attempt == 1
    assert result.records[0].stop_reason == "length"
    assert result.records[0].error_type == "TruncatedResponseError"
    assert result.records[0].output_tokens == 256
    assert result.records[0].response_text == "cut"


def test_transient_failure_retries_up_to_three_and_records_each(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("down")
        return http_response(200, payload(response="recovered", prompt_eval_count=8, eval_count=4))

    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", fake_post)
    sleeps: list[float] = []
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", sleeps.append)
    monkeypatch.setattr("promptlab.adapters.ollama.random.uniform", lambda _low, _high: 0.0)

    result = adapter().complete(request(), "run-retry")

    assert calls == 3
    assert len(sleeps) == 2
    assert sleeps[1] == pytest.approx(sleeps[0] * 2)
    assert all(delay > 0 for delay in sleeps)
    assert result.succeeded is True
    assert result.text == "recovered"
    assert [record.attempt for record in result.records] == [1, 2, 3]
    assert [record.error_type for record in result.records] == [
        "TransientProviderError",
        "TransientProviderError",
        None,
    ]
    assert result.records[0].response_text is None
    assert result.records[0].input_tokens == 0
    assert result.records[0].cost_usd == pytest.approx(0.0)
    assert result.records[2].response_text == "recovered"


def test_persistent_transient_failure_stops_at_three(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", fake_post)
    sleeps: list[float] = []
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", sleeps.append)

    result = adapter().complete(request(), "run-down")

    assert calls == 3
    assert len(sleeps) == 2
    assert result.succeeded is False
    assert result.text is None
    assert result.error_type == "TransientProviderError"
    assert len(result.records) == 3
    assert all(record.error_type == "TransientProviderError" for record in result.records)


def test_server_5xx_is_retried_and_4xx_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = iter([503, 400])
    calls = 0

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        nonlocal calls
        calls += 1
        return http_response(next(statuses))

    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", fake_post)
    sleeps: list[float] = []
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", sleeps.append)

    result = adapter().complete(request(), "run-http")

    assert calls == 2
    assert len(sleeps) == 1
    assert result.succeeded is False
    assert result.error_type == "PermanentProviderError"
    assert [record.error_type for record in result.records] == [
        "TransientProviderError",
        "PermanentProviderError",
    ]


def test_unavailable_model_is_permanent_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        nonlocal calls
        calls += 1
        return http_response(404, {"error": "model not found"})

    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", fake_post)
    sleeps: list[float] = []
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", sleeps.append)

    result = adapter().complete(request(), "run-missing")

    assert calls == 1
    assert sleeps == []
    assert result.error_type == "PermanentProviderError"
    assert result.records[0].attempt == 1
    assert result.records[0].response_text is None


def test_unknown_model_raises_before_any_call(monkeypatch: pytest.MonkeyPatch) -> None:
    posted = MagicMock()
    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", posted)

    client = OllamaAdapter(model_id="not-configured", base_url="http://ollama.test")

    with pytest.raises(UnknownModelError):
        client.complete(request(), "run-unknown")

    posted.assert_not_called()


def test_attempt_cap_stays_at_three_even_if_config_asks_for_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.from_env()
    loud = Settings(
        ollama_base_url=settings.ollama_base_url,
        models=settings.models,
        temperature=settings.temperature,
        max_retries=20,
        max_schema_repairs=settings.max_schema_repairs,
        per_run_cap_usd=settings.per_run_cap_usd,
        weekly_cap_usd=settings.weekly_cap_usd,
    )
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: loud))

    calls = 0

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("down")

    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", fake_post)
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", lambda _delay: None)

    result = adapter().complete(request(), "run-cap")

    assert calls == 3
    assert len(result.records) == 3
