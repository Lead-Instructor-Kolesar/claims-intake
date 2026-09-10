"""Day 1: instrument real local Mistral calls and append usage records."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from promptlab.config import PROJECT_ROOT, Settings
from promptlab.usage import CallRecord, append_record, compute_cost

CASE_IDS = ("E12", "E07", "E11")
PROMPT_ID = "baseline"
PROMPT_VERSION = "v0"
DEFAULT_MAX_OUTPUT_TOKENS = 256
TRUNCATION_MAX_OUTPUT_TOKENS = 8
TASK: Literal["extraction"] = "extraction"


def load_cases(path: Path, case_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    wanted = set(case_ids)
    found: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            case = json.loads(line)
            case_id = str(case["id"])
            if case_id in wanted:
                found[case_id] = case
    missing = [case_id for case_id in case_ids if case_id not in found]
    if missing:
        raise KeyError(f"Missing extraction cases: {', '.join(missing)}")
    return [found[case_id] for case_id in case_ids]


def call_ollama(
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


def build_record(
    *,
    run_id: str,
    model_id: str,
    case_id: str,
    temperature: float,
    max_output_tokens: int,
    payload: dict[str, Any],
    latency_ms: int,
    error_type: str | None = None,
) -> CallRecord:
    input_tokens = int(payload["prompt_eval_count"])
    output_tokens = int(payload["eval_count"])
    stop_reason = payload.get("done_reason")
    response_text = payload.get("response")
    return CallRecord(
        record_id=str(uuid.uuid4()),
        run_id=run_id,
        timestamp=datetime.now(UTC),
        provider="ollama",
        model_id=model_id,
        task=TASK,
        case_id=case_id,
        prompt_id=PROMPT_ID,
        prompt_version=PROMPT_VERSION,
        attempt=1,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=None,
        latency_ms=latency_ms,
        cost_usd=compute_cost(model_id, input_tokens, output_tokens),
        stop_reason=str(stop_reason) if stop_reason is not None else None,
        error_type=error_type,
        response_text=str(response_text) if response_text is not None else None,
    )


def main() -> None:
    settings = Settings.from_env()
    model_id = settings.models["mistral"].model_id
    temperature = 0.0
    run_id = str(uuid.uuid4())

    cases_path = PROJECT_ROOT / "cases" / "extraction.jsonl"
    prompt_path = PROJECT_ROOT / "src" / "prompts" / "baseline.v0.md"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    cases = load_cases(cases_path, CASE_IDS)

    for case in cases:
        prompt = prompt_template.replace("{document_text}", str(case["source"]))
        payload, latency_ms = call_ollama(
            base_url=settings.ollama_base_url,
            model_id=model_id,
            prompt=prompt,
            temperature=temperature,
            num_predict=DEFAULT_MAX_OUTPUT_TOKENS,
        )
        record = build_record(
            run_id=run_id,
            model_id=model_id,
            case_id=str(case["id"]),
            temperature=temperature,
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
            payload=payload,
            latency_ms=latency_ms,
        )
        append_record(record, run_id)

    e11 = next(case for case in cases if case["id"] == "E11")
    truncated_prompt = prompt_template.replace("{document_text}", str(e11["source"]))
    truncated_payload, truncated_latency_ms = call_ollama(
        base_url=settings.ollama_base_url,
        model_id=model_id,
        prompt=truncated_prompt,
        temperature=temperature,
        num_predict=TRUNCATION_MAX_OUTPUT_TOKENS,
    )
    error_type = (
        "TruncatedResponseError" if truncated_payload.get("done_reason") == "length" else None
    )
    truncated_record = build_record(
        run_id=run_id,
        model_id=model_id,
        case_id="E11",
        temperature=temperature,
        max_output_tokens=TRUNCATION_MAX_OUTPUT_TOKENS,
        payload=truncated_payload,
        latency_ms=truncated_latency_ms,
        error_type=error_type,
    )
    append_record(truncated_record, run_id)
    print(f"run_id={run_id}")
    print(
        "truncation done_reason="
        f"{truncated_payload.get('done_reason')} error_type={error_type}"
    )


if __name__ == "__main__":
    main()
