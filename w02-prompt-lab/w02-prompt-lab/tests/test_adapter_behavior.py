"""Adapter contract tests. These mock HTTP and do not call Ollama."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.adapters.ollama import MAX_ATTEMPTS, OllamaAdapter
from promptlab.config import Settings
from promptlab.errors import (
    PermanentProviderError,
    TransientProviderError,
    TruncatedResponseError,
    UnknownModelError,
)
from promptlab.usage import CallRecord

OLLAMA_FIELDS = ("prompt_eval_count", "eval_count", "done_reason")


def make_request() -> CompletionRequest:
    return CompletionRequest(
        task="summarization",
        case_id="S01",
        prompt_id="baseline",
        prompt_version="v0",
        system="Summarize the document.",
        user_content="A short policy document.",
        temperature=0.0,
        max_output_tokens=256,
    )


def configured_adapter() -> OllamaAdapter:
    settings = Settings.from_env()
    model = next(iter(settings.models.values()))
    return OllamaAdapter(model_id=model.model_id, base_url=settings.ollama_base_url)


def test_protocol_and_result_shapes_match_the_contract() -> None:
    adapter: ModelAdapter = configured_adapter()
    assert adapter.provider == "ollama"
    assert isinstance(adapter.model_id, str)
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
    assert set(CompletionResult.model_fields) == {"succeeded", "text", "error_type", "records"}


def test_unknown_model_id_raises_without_a_network_call() -> None:
    settings = Settings.from_env()
    with pytest.raises(UnknownModelError):
        OllamaAdapter(model_id="not-a-configured-model", base_url=settings.ollama_base_url)


def test_successful_completion_records_one_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    adapter = configured_adapter()

    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "response": "summary",
                "prompt_eval_count": 11,
                "eval_count": 7,
                "done_reason": "stop",
            }

    def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", fake_post)
    result = adapter.complete(make_request(), "run-ok")
    assert captured["json"]["think"] is False
    assert captured["json"]["options"]["num_predict"] == make_request().max_output_tokens

    assert result.succeeded is True
    assert result.text == "summary"
    assert result.error_type is None
    assert len(result.records) == 1
    record = result.records[0]
    assert isinstance(record, CallRecord)
    assert record.attempt == 1
    assert record.input_tokens == 11
    assert record.output_tokens == 7
    assert record.stop_reason == "stop"
    assert record.provider == "ollama"
    assert record.cost_usd == 0.0
    lines = (tmp_path / "runs" / "run-ok.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_transient_failure_retries_with_backoff_and_records_every_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    adapter = configured_adapter()
    sleeps: list[float] = []
    posts = {"count": 0}

    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        posts["count"] += 1
        if posts["count"] < 3:
            raise httpx.TimeoutException("temporary timeout")
        response = httpx.Response(
            200,
            json={
                "response": "recovered",
                "prompt_eval_count": 4,
                "eval_count": 2,
                "done_reason": "stop",
            },
        )
        return response

    monkeypatch.setattr("promptlab.adapters.ollama.httpx.post", fake_post)
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", sleeps.append)

    result = adapter.complete(make_request(), "run-retry")
    assert result.succeeded is True
    assert result.text == "recovered"
    assert posts["count"] == 3
    assert len(result.records) == 3
    assert [record.attempt for record in result.records] == [1, 2, 3]
    assert result.records[0].error_type == TransientProviderError.__name__
    assert result.records[1].error_type == TransientProviderError.__name__
    assert result.records[2].error_type is None
    assert len(sleeps) == 2
    assert all(delay > 0 for delay in sleeps)


def test_transient_failures_stop_at_three_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    adapter = configured_adapter()
    monkeypatch.setattr(
        "promptlab.adapters.ollama.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("down")),
    )
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", lambda delay: None)

    result = adapter.complete(make_request(), "run-exhausted")
    assert result.succeeded is False
    assert result.error_type == TransientProviderError.__name__
    assert len(result.records) == MAX_ATTEMPTS
    assert [record.attempt for record in result.records] == [1, 2, 3]


def test_permanent_failure_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    adapter = configured_adapter()
    sleeps: list[float] = []

    class FakeResponse:
        status_code = 400

        def json(self) -> dict[str, Any]:
            return {"error": "bad request"}

    monkeypatch.setattr(
        "promptlab.adapters.ollama.httpx.post",
        lambda *args, **kwargs: FakeResponse(),
    )
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", sleeps.append)

    result = adapter.complete(make_request(), "run-permanent")
    assert result.succeeded is False
    assert result.error_type == PermanentProviderError.__name__
    assert len(result.records) == 1
    assert result.records[0].attempt == 1
    assert sleeps == []


def test_truncation_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    adapter = configured_adapter()
    sleeps: list[float] = []

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "response": "cut off",
                "prompt_eval_count": 20,
                "eval_count": 8,
                "done_reason": "length",
            }

    monkeypatch.setattr(
        "promptlab.adapters.ollama.httpx.post",
        lambda *args, **kwargs: FakeResponse(),
    )
    monkeypatch.setattr("promptlab.adapters.ollama.time.sleep", sleeps.append)

    result = adapter.complete(make_request(), "run-trunc")
    assert result.succeeded is False
    assert result.error_type == TruncatedResponseError.__name__
    assert result.text == "cut off"
    assert len(result.records) == 1
    assert result.records[0].stop_reason == "length"
    assert sleeps == []


def test_same_adapter_class_can_wrap_each_configured_model() -> None:
    settings = Settings.from_env()
    adapters = [
        OllamaAdapter(model_id=model.model_id, base_url=settings.ollama_base_url)
        for model in settings.models.values()
    ]
    assert len(adapters) == 2
    assert adapters[0].__class__ is adapters[1].__class__
    assert {adapter.model_id for adapter in adapters} == {
        model.model_id for model in settings.models.values()
    }
    assert all(adapter.provider == "ollama" for adapter in adapters)


def test_ollama_response_field_names_stay_inside_adapters() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "promptlab"
    checked = [root / "day2.py", root / "errors.py", root / "usage.py", root / "config.py"]
    leaked: list[str] = []
    for path in checked:
        text = path.read_text(encoding="utf-8")
        for field in OLLAMA_FIELDS:
            if field in text:
                leaked.append(f"{path.name}:{field}")
    assert leaked == []


def test_day2_has_no_model_identifier_literals() -> None:
    src_root = Path(__file__).resolve().parents[1] / "src" / "promptlab"
    source = (src_root / "day2.py").read_text()
    adapter = (src_root / "adapters" / "ollama.py").read_text()
    for blob in (source, adapter):
        assert "mistral:7b" not in blob
        assert "qwen3:8b" not in blob
