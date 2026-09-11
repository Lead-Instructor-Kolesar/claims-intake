"""Day 1: instrument three local Ollama extraction calls."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from promptlab.config import PROJECT_ROOT, ModelConfig, Settings
from promptlab.usage import CallRecord, append_record, compute_cost

CASE_IDS = ("E12", "E07", "E11")
MAX_OUTPUT_TOKENS = 256
TRUNCATION_NUM_PREDICT = 8
TEMPERATURE = 0.0
PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "baseline.v0.md"
CASES_PATH = PROJECT_ROOT / "cases" / "extraction.jsonl"


def load_cases(case_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    lines = CASES_PATH.read_text(encoding="utf-8").splitlines()
    by_id = {
        row["id"]: row
        for row in (json.loads(line) for line in lines if line.strip())
    }
    return [by_id[case_id] for case_id in case_ids]


def generate(
    *,
    base_url: str,
    model_id: str,
    prompt: str,
    temperature: float,
    num_predict: int,
) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    response = httpx.post(
        f"{base_url}/api/generate",
        json={
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
        },
        timeout=180.0,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload, latency_ms


def stop_error(stop_reason: str | None) -> str | None:
    if stop_reason == "length":
        return "TruncatedResponseError"
    return None


def build_record(
    *,
    case: dict[str, Any],
    payload: dict[str, Any],
    latency_ms: int,
    run_id: str,
    num_predict: int,
    model: ModelConfig,
) -> CallRecord:
    input_tokens = int(payload["prompt_eval_count"])
    output_tokens = int(payload["eval_count"])
    stop_reason = payload.get("done_reason")
    if stop_reason is not None:
        stop_reason = str(stop_reason)
    return CallRecord(
        record_id=str(uuid4()),
        run_id=run_id,
        timestamp=datetime.now(UTC),
        provider="ollama",
        model_id=model.model_id,
        task="extraction",
        case_id=case["id"],
        prompt_id="baseline",
        prompt_version="v0",
        attempt=1,
        temperature=TEMPERATURE,
        max_output_tokens=num_predict,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=None,
        latency_ms=latency_ms,
        cost_usd=compute_cost(model.model_id, input_tokens, output_tokens),
        stop_reason=stop_reason,
        error_type=stop_error(stop_reason),
        response_text=payload.get("response"),
    )


def build_error_record(
    *,
    case: dict[str, Any],
    latency_ms: int,
    run_id: str,
    num_predict: int,
    model: ModelConfig,
    error: Exception,
) -> CallRecord:
    input_tokens = 0
    output_tokens = 0
    return CallRecord(
        record_id=str(uuid4()),
        run_id=run_id,
        timestamp=datetime.now(UTC),
        provider="ollama",
        model_id=model.model_id,
        task="extraction",
        case_id=case["id"],
        prompt_id="baseline",
        prompt_version="v0",
        attempt=1,
        temperature=TEMPERATURE,
        max_output_tokens=num_predict,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=None,
        latency_ms=latency_ms,
        cost_usd=compute_cost(model.model_id, input_tokens, output_tokens),
        stop_reason=None,
        error_type=type(error).__name__,
        response_text=None,
    )


def run_case(
    *,
    case: dict[str, Any],
    prompt: str,
    base_url: str,
    model: ModelConfig,
    run_id: str,
    num_predict: int,
) -> CallRecord:
    started = time.perf_counter()
    try:
        payload, latency_ms = generate(
            base_url=base_url,
            model_id=model.model_id,
            prompt=prompt,
            temperature=TEMPERATURE,
            num_predict=num_predict,
        )
        return build_record(
            case=case,
            payload=payload,
            latency_ms=latency_ms,
            run_id=run_id,
            num_predict=num_predict,
            model=model,
        )
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return build_error_record(
            case=case,
            latency_ms=latency_ms,
            run_id=run_id,
            num_predict=num_predict,
            model=model,
            error=err,
        )


def main() -> None:
    settings = Settings.from_env()
    model = settings.models["mistral"]
    template = PROMPT_PATH.read_text(encoding="utf-8")
    cases = load_cases(CASE_IDS)
    run_id = str(uuid4())

    for case in cases:
        prompt = template.replace("{document_text}", case["source"])
        record = run_case(
            case=case,
            prompt=prompt,
            base_url=settings.ollama_base_url,
            model=model,
            run_id=run_id,
            num_predict=MAX_OUTPUT_TOKENS,
        )
        append_record(record, run_id)
        print(
            f"{case['id']}: {record.input_tokens} in / "
            f"{record.output_tokens} out / {record.latency_ms} ms"
            f" error={record.error_type}"
        )

    print(f"wrote runs/{run_id}.jsonl")

    # Deliberate low ceiling on E11 to force done_reason=length.
    e11 = next(case for case in cases if case["id"] == "E11")
    trunc_run_id = f"{run_id}-truncation"
    trunc_prompt = template.replace("{document_text}", e11["source"])
    trunc_record = run_case(
        case=e11,
        prompt=trunc_prompt,
        base_url=settings.ollama_base_url,
        model=model,
        run_id=trunc_run_id,
        num_predict=TRUNCATION_NUM_PREDICT,
    )
    append_record(trunc_record, trunc_run_id)
    print(
        f"E11 truncation: stop_reason={trunc_record.stop_reason} "
        f"error_type={trunc_record.error_type}"
    )
    print(f"wrote runs/{trunc_run_id}.jsonl")


if __name__ == "__main__":
    main()
