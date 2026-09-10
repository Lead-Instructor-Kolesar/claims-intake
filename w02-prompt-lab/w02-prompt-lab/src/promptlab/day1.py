"""Day 1 runner: instrument Mistral extraction calls through Ollama."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from promptlab.config import PROJECT_ROOT, Settings
from promptlab.usage import CallRecord, append_record, compute_cost

SELECTED_CASE_IDS = ("E12", "E07", "E11")
NORMAL_NUM_PREDICT = 256
TRUNCATION_NUM_PREDICT = 8
TEMPERATURE = 0.0
PROMPT_ID = "baseline"
PROMPT_VERSION = "v0"
CASES_PATH = PROJECT_ROOT / "cases" / "extraction.jsonl"
PROMPT_PATH = PROJECT_ROOT / "src" / "prompts" / "baseline.v0.md"


def load_selected_cases(path: Path, case_ids: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    wanted = set(case_ids)
    selected: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case: dict[str, Any] = json.loads(line)
        case_id = str(case["id"])
        if case_id in wanted:
            selected[case_id] = case
    missing = [case_id for case_id in case_ids if case_id not in selected]
    if missing:
        raise KeyError(f"Missing extraction cases: {', '.join(missing)}")
    return selected


def call_ollama(
    settings: Settings,
    model_id: str,
    prompt: str,
    temperature: float,
    num_predict: int,
) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    response = httpx.post(
        f"{settings.ollama_base_url}/api/generate",
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
    payload: dict[str, Any],
    latency_ms: int,
    temperature: float,
    max_output_tokens: int,
    error_type: str | None,
) -> CallRecord:
    input_tokens = int(payload.get("prompt_eval_count") or 0)
    output_tokens = int(payload.get("eval_count") or 0)
    stop_reason = payload.get("done_reason")
    response_text = payload.get("response")
    return CallRecord(
        record_id=str(uuid4()),
        run_id=run_id,
        timestamp=datetime.now(UTC),
        provider="ollama",
        model_id=model_id,
        task="extraction",
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
        stop_reason=None if stop_reason is None else str(stop_reason),
        error_type=error_type,
        response_text=None if response_text is None else str(response_text),
    )


def main() -> None:
    settings = Settings.from_env()
    model_id = settings.models["mistral"].model_id
    run_id = str(uuid4())
    cases = load_selected_cases(CASES_PATH, SELECTED_CASE_IDS)
    template = PROMPT_PATH.read_text(encoding="utf-8")

    truncated_prompt = template.replace("{document_text}", str(cases["E11"]["source"]))
    truncated_payload, truncated_latency_ms = call_ollama(
        settings,
        model_id,
        truncated_prompt,
        TEMPERATURE,
        TRUNCATION_NUM_PREDICT,
    )
    truncated_stop = truncated_payload.get("done_reason")
    truncated_error = (
        "TruncatedResponseError" if truncated_stop == "length" else None
    )
    append_record(
        build_record(
            run_id=run_id,
            model_id=model_id,
            case_id="E11",
            payload=truncated_payload,
            latency_ms=truncated_latency_ms,
            temperature=TEMPERATURE,
            max_output_tokens=TRUNCATION_NUM_PREDICT,
            error_type=truncated_error,
        ),
        run_id,
    )

    for case_id in SELECTED_CASE_IDS:
        case = cases[case_id]
        prompt = template.replace("{document_text}", str(case["source"]))
        payload, latency_ms = call_ollama(
            settings,
            model_id,
            prompt,
            TEMPERATURE,
            NORMAL_NUM_PREDICT,
        )
        append_record(
            build_record(
                run_id=run_id,
                model_id=model_id,
                case_id=case_id,
                payload=payload,
                latency_ms=latency_ms,
                temperature=TEMPERATURE,
                max_output_tokens=NORMAL_NUM_PREDICT,
                error_type=None,
            ),
            run_id,
        )

    print(f"run_id={run_id}")
    print(f"records=runs/{run_id}.jsonl")


if __name__ == "__main__":
    main()
