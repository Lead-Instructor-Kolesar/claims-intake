from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from promptlab.adapters.base import CompletionRequest
from promptlab.adapters.ollama import OllamaAdapter
from promptlab.config import Settings
from promptlab.errors import (
    PermanentProviderError,
    TransientProviderError,
    UnknownModelError,
)


def _model_id() -> str:
    return Settings.from_env().models["mistral"].model_id


def _request() -> CompletionRequest:
    return CompletionRequest(
        task="summarization",
        case_id="S01",
        prompt_id="baseline",
        prompt_version="v0",
        system="system",
        user_content="user",
        temperature=0.0,
        max_output_tokens=64,
    )


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "ok",
        payload: dict[str, Any] | list[Any] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def test_unknown_model_raises_before_http(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[object] = []

    def capture(*args: object, **kwargs: object) -> None:
        posted.append(1)

    monkeypatch.setattr(httpx, "post", capture)

    adapter = OllamaAdapter(model_id="not-a-configured-model")
    with pytest.raises(UnknownModelError):
        adapter.complete(_request(), "run-unknown")
    assert posted == []


def test_exhausted_transient_failures_stop_at_three(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def always_down(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", always_down)
    monkeypatch.setattr("time.sleep", lambda _: None)

    result = OllamaAdapter(model_id=_model_id()).complete(_request(), "run-down")

    assert calls == 3
    assert result.succeeded is False
    assert result.error_type == TransientProviderError.__name__
    assert [record.attempt for record in result.records] == [1, 2, 3]


def test_server_error_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def flaky(*args: object, **kwargs: object) -> FakeResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return FakeResponse(status_code=503, text="")
        return FakeResponse(
            payload={
                "response": "ok",
                "prompt_eval_count": 4,
                "eval_count": 2,
                "done_reason": "stop",
            }
        )

    monkeypatch.setattr(httpx, "post", flaky)
    monkeypatch.setattr("time.sleep", lambda _: None)

    result = OllamaAdapter(model_id=_model_id()).complete(_request(), "run-503")

    assert calls == 2
    assert result.succeeded is True
    assert result.records[0].error_type == TransientProviderError.__name__
    assert result.records[0].error_type != PermanentProviderError.__name__


def test_malformed_json_is_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            json_error=json.JSONDecodeError("bad", "x", 0)
        ),
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    result = OllamaAdapter(model_id=_model_id()).complete(_request(), "run-json")

    assert result.succeeded is False
    assert result.error_type == TransientProviderError.__name__
    assert len(result.records) == 3


def test_non_object_body_is_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(payload=["not", "an", "object"]),
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    result = OllamaAdapter(model_id=_model_id()).complete(_request(), "run-list")

    assert result.succeeded is False
    assert result.error_type == TransientProviderError.__name__
    assert len(result.records) == 3


def test_error_object_without_response_is_permanent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(payload={"error": "model is busy"}),
    )

    result = OllamaAdapter(model_id=_model_id()).complete(_request(), "run-err")

    assert result.succeeded is False
    assert result.error_type == PermanentProviderError.__name__
    assert len(result.records) == 1


def test_missing_token_counts_are_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(payload={"response": "text only"}),
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    result = OllamaAdapter(model_id=_model_id()).complete(_request(), "run-tokens")

    assert result.succeeded is False
    assert result.error_type == TransientProviderError.__name__
    assert len(result.records) == 3
