from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import httpx
import pytest

from promptlab import day1
from promptlab.config import ModelConfig, Settings


def mistral_model() -> ModelConfig:
    return Settings.from_env().models["mistral"]


def sample_case(case_id: str = "E12") -> dict[str, Any]:
    return {"id": case_id, "source": "short document text"}


def ollama_payload(
    *,
    response: str = "ok",
    prompt_eval_count: int = 40,
    eval_count: int = 12,
    done_reason: str | None = "stop",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "response": response,
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
    }
    if done_reason is not None:
        payload["done_reason"] = done_reason
    return payload


def test_load_cases_returns_requested_order() -> None:
    cases = day1.load_cases(day1.CASE_IDS)

    assert [case["id"] for case in cases] == ["E12", "E07", "E11"]
    assert all("source" in case and case["source"] for case in cases)


def test_stop_error_maps_length_to_truncated() -> None:
    assert day1.stop_error("length") == "TruncatedResponseError"
    assert day1.stop_error("stop") is None
    assert day1.stop_error(None) is None


def test_build_record_maps_ollama_fields() -> None:
    model = mistral_model()
    record = day1.build_record(
        case=sample_case("E07"),
        payload=ollama_payload(
            response="extracted",
            prompt_eval_count=111,
            eval_count=22,
            done_reason="stop",
        ),
        latency_ms=321,
        run_id="run-a",
        num_predict=256,
        model=model,
    )

    assert record.provider == "ollama"
    assert record.model_id == model.model_id
    assert record.task == "extraction"
    assert record.case_id == "E07"
    assert record.prompt_id == "baseline"
    assert record.prompt_version == "v0"
    assert record.attempt == 1
    assert record.temperature == 0.0
    assert record.max_output_tokens == 256
    assert record.input_tokens == 111
    assert record.output_tokens == 22
    assert record.cached_input_tokens is None
    assert record.latency_ms == 321
    assert record.cost_usd == pytest.approx(0.0)
    assert record.stop_reason == "stop"
    assert record.error_type is None
    assert record.response_text == "extracted"
    assert record.timestamp.tzinfo is not None
    assert record.timestamp.utcoffset() is not None
    assert record.record_id
    assert record.run_id == "run-a"


def test_build_record_marks_truncation() -> None:
    record = day1.build_record(
        case=sample_case("E11"),
        payload=ollama_payload(done_reason="length", eval_count=8),
        latency_ms=50,
        run_id="run-trunc",
        num_predict=8,
        model=mistral_model(),
    )

    assert record.stop_reason == "length"
    assert record.error_type == "TruncatedResponseError"
    assert record.max_output_tokens == 8


def test_build_error_record_captures_exception_type() -> None:
    record = day1.build_error_record(
        case=sample_case(),
        latency_ms=17,
        run_id="run-err",
        num_predict=256,
        model=mistral_model(),
        error=httpx.ConnectError("down"),
    )

    assert record.input_tokens == 0
    assert record.output_tokens == 0
    assert record.cost_usd == pytest.approx(0.0)
    assert record.stop_reason is None
    assert record.error_type == "ConnectError"
    assert record.response_text is None
    assert record.latency_ms == 17


def test_generate_posts_expected_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> MagicMock:
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["timeout"] = kwargs["timeout"]
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value=ollama_payload())
        return response

    monkeypatch.setattr(httpx, "post", fake_post)

    payload, latency_ms = day1.generate(
        base_url="http://ollama.test",
        model_id="mistral:7b",
        prompt="hello",
        temperature=0.0,
        num_predict=256,
    )

    assert captured["url"] == "http://ollama.test/api/generate"
    assert captured["timeout"] == 180.0
    assert captured["json"] == {
        "model": "mistral:7b",
        "prompt": "hello",
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 256},
    }
    assert payload["prompt_eval_count"] == 40
    assert latency_ms >= 0


def test_run_case_success_builds_call_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        day1,
        "generate",
        lambda **_: (ollama_payload(prompt_eval_count=9, eval_count=3), 44),
    )

    record = day1.run_case(
        case=sample_case("E12"),
        prompt="prompt",
        base_url="http://ollama.test",
        model=mistral_model(),
        run_id="run-ok",
        num_predict=256,
    )

    assert record.case_id == "E12"
    assert record.input_tokens == 9
    assert record.output_tokens == 3
    assert record.latency_ms == 44
    assert record.error_type is None


def test_run_case_http_error_returns_error_record(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**_: Any) -> tuple[dict[str, Any], int]:
        raise httpx.HTTPStatusError(
            "bad",
            request=httpx.Request("POST", "http://ollama.test/api/generate"),
            response=httpx.Response(500),
        )

    monkeypatch.setattr(day1, "generate", boom)

    record = day1.run_case(
        case=sample_case("E11"),
        prompt="prompt",
        base_url="http://ollama.test",
        model=mistral_model(),
        run_id="run-http",
        num_predict=256,
    )

    assert record.error_type == "HTTPStatusError"
    assert record.response_text is None
    assert record.input_tokens == 0


def test_run_case_missing_token_fields_returns_error_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(day1, "generate", lambda **_: ({"response": "x"}, 10))

    record = day1.run_case(
        case=sample_case(),
        prompt="prompt",
        base_url="http://ollama.test",
        model=mistral_model(),
        run_id="run-key",
        num_predict=256,
    )

    assert record.error_type == "KeyError"
    assert record.stop_reason is None


def test_main_runs_three_cases_then_truncation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    model = ModelConfig(
        logical_name="mistral",
        model_id="mistral:7b",
        input_usd_per_million=Decimal("0"),
        output_usd_per_million=Decimal("0"),
    )
    settings = Settings(
        ollama_base_url="http://ollama.test",
        models={"mistral": model, "qwen": model},
        temperature=0.0,
        max_retries=2,
        max_schema_repairs=1,
        per_run_cap_usd=Decimal("2.00"),
        weekly_cap_usd=Decimal("25.00"),
    )
    cases = [
        {"id": "E12", "source": "short"},
        {"id": "E07", "source": "mid"},
        {"id": "E11", "source": "long"},
    ]
    calls: list[dict[str, Any]] = []
    appended: list[tuple[str, str]] = []

    def fake_run_case(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return day1.build_record(
            case=kwargs["case"],
            payload=ollama_payload(
                done_reason=(
                    "length"
                    if kwargs["num_predict"] == day1.TRUNCATION_NUM_PREDICT
                    else "stop"
                ),
                eval_count=kwargs["num_predict"],
            ),
            latency_ms=1,
            run_id=kwargs["run_id"],
            num_predict=kwargs["num_predict"],
            model=kwargs["model"],
        )

    def fake_append(record: Any, run_id: str) -> None:
        appended.append((record.case_id, run_id))

    def fake_from_env(*_args: object, **_kwargs: object) -> Settings:
        return settings

    prompt_path = MagicMock()
    prompt_path.read_text.return_value = "DOC:{document_text}"

    monkeypatch.setattr(Settings, "from_env", fake_from_env)
    monkeypatch.setattr(day1, "load_cases", lambda _ids: cases)
    monkeypatch.setattr(day1, "PROMPT_PATH", prompt_path)
    monkeypatch.setattr(day1, "run_case", fake_run_case)
    monkeypatch.setattr(day1, "append_record", fake_append)
    monkeypatch.setattr(
        day1,
        "uuid4",
        lambda: UUID("00000000-0000-4000-8000-0000000000aa"),
    )

    day1.main()
    out = capsys.readouterr().out
    run_id = "00000000-0000-4000-8000-0000000000aa"

    assert len(calls) == 4
    assert [c["case"]["id"] for c in calls[:3]] == ["E12", "E07", "E11"]
    assert all(c["num_predict"] == day1.MAX_OUTPUT_TOKENS for c in calls[:3])
    assert all(c["run_id"] == run_id for c in calls[:3])
    assert calls[3]["case"]["id"] == "E11"
    assert calls[3]["num_predict"] == day1.TRUNCATION_NUM_PREDICT
    assert calls[3]["run_id"] == f"{run_id}-truncation"
    assert [item[0] for item in appended] == ["E12", "E07", "E11", "E11"]
    assert appended[3][1] == f"{run_id}-truncation"
    assert f"wrote runs/{run_id}.jsonl" in out
    assert "TruncatedResponseError" in out
    assert "E12:" in out
    assert isinstance(calls[0]["model"], ModelConfig)
    assert calls[0]["prompt"] == "DOC:short"
    assert calls[3]["prompt"] == "DOC:long"
