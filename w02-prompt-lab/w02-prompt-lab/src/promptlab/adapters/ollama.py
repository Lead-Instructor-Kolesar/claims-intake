"""Ollama-backed ModelAdapter with transient retry."""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

import httpx

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.config import Settings
from promptlab.errors import (
    PermanentProviderError,
    TransientProviderError,
    TruncatedResponseError,
    UnknownModelError,
)
from promptlab.usage import CallRecord, compute_cost

_PERMANENT_STATUS_CODES = {400, 404, 422}


class OllamaAdapter:
    provider = "ollama"

    def __init__(self, model_id: str) -> None:
        known_ids = {config.model_id for config in Settings.from_env().models.values()}
        if model_id not in known_ids:
            raise UnknownModelError(model_id)
        self.model_id = model_id

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        settings = Settings.from_env()
        max_attempts = min(1 + settings.max_retries, 3)
        url = f"{settings.ollama_base_url}/api/generate"
        records: list[CallRecord] = []

        for attempt in range(1, max_attempts + 1):
            started = perf_counter()
            text: str | None = None
            input_tokens = 0
            output_tokens = 0
            stop_reason: str | None = None

            try:
                try:
                    response = httpx.post(
                        url,
                        json={
                            "model": self.model_id,
                            "prompt": f"{request.system}\n\n{request.user_content}",
                            "stream": False,
                            "options": {
                                "temperature": request.temperature,
                                "num_predict": request.max_output_tokens,
                            },
                        },
                        timeout=180.0,
                    )
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    raise TransientProviderError(str(exc)) from exc

                status_code = getattr(response, "status_code", None)
                if status_code in _PERMANENT_STATUS_CODES:
                    raise PermanentProviderError(
                        f"Ollama returned HTTP {status_code}"
                    )
                if isinstance(status_code, int) and status_code >= 500:
                    raise TransientProviderError(
                        f"Ollama returned HTTP {status_code}"
                    )

                try:
                    payload = response.json()
                except Exception as exc:
                    raise PermanentProviderError(
                        "Ollama returned an unparseable body"
                    ) from exc

                if not isinstance(payload, dict):
                    raise PermanentProviderError(
                        "Ollama returned an unparseable body"
                    )

                raw_text = payload.get("response")
                if not raw_text:
                    message = payload.get("message")
                    if isinstance(message, dict):
                        raw_text = message.get("content")
                text = raw_text if isinstance(raw_text, str) else None
                input_tokens = int(payload.get("prompt_eval_count") or 0)
                output_tokens = int(payload.get("eval_count") or 0)
                done_reason = payload.get("done_reason")
                stop_reason = str(done_reason) if done_reason is not None else None
                if stop_reason == "length":
                    raise TruncatedResponseError(
                        "Response truncated by output-token ceiling"
                    )

                latency_ms = int((perf_counter() - started) * 1000)
                record = CallRecord(
                    record_id=str(uuid4()),
                    run_id=run_id,
                    timestamp=datetime.now(UTC),
                    provider="ollama",
                    model_id=self.model_id,
                    task=request.task,
                    case_id=request.case_id,
                    prompt_id=request.prompt_id,
                    prompt_version=request.prompt_version,
                    attempt=attempt,
                    temperature=request.temperature,
                    max_output_tokens=request.max_output_tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_input_tokens=None,
                    latency_ms=latency_ms,
                    cost_usd=compute_cost(self.model_id, input_tokens, output_tokens),
                    stop_reason=stop_reason,
                    error_type=None,
                    response_text=text,
                )
                records.append(record)
                return CompletionResult(
                    succeeded=True,
                    text=text,
                    error_type=None,
                    records=records,
                )

            except TruncatedResponseError as exc:
                latency_ms = int((perf_counter() - started) * 1000)
                error_type = type(exc).__name__
                records.append(
                    CallRecord(
                        record_id=str(uuid4()),
                        run_id=run_id,
                        timestamp=datetime.now(UTC),
                        provider="ollama",
                        model_id=self.model_id,
                        task=request.task,
                        case_id=request.case_id,
                        prompt_id=request.prompt_id,
                        prompt_version=request.prompt_version,
                        attempt=attempt,
                        temperature=request.temperature,
                        max_output_tokens=request.max_output_tokens,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cached_input_tokens=None,
                        latency_ms=latency_ms,
                        cost_usd=compute_cost(
                            self.model_id, input_tokens, output_tokens
                        ),
                        stop_reason=stop_reason,
                        error_type=error_type,
                        response_text=text,
                    )
                )
                return CompletionResult(
                    succeeded=False,
                    text=text,
                    error_type=error_type,
                    records=records,
                )

            except PermanentProviderError as exc:
                latency_ms = int((perf_counter() - started) * 1000)
                error_type = type(exc).__name__
                records.append(
                    CallRecord(
                        record_id=str(uuid4()),
                        run_id=run_id,
                        timestamp=datetime.now(UTC),
                        provider="ollama",
                        model_id=self.model_id,
                        task=request.task,
                        case_id=request.case_id,
                        prompt_id=request.prompt_id,
                        prompt_version=request.prompt_version,
                        attempt=attempt,
                        temperature=request.temperature,
                        max_output_tokens=request.max_output_tokens,
                        input_tokens=0,
                        output_tokens=0,
                        cached_input_tokens=None,
                        latency_ms=latency_ms,
                        cost_usd=compute_cost(self.model_id, 0, 0),
                        stop_reason=None,
                        error_type=error_type,
                        response_text=None,
                    )
                )
                return CompletionResult(
                    succeeded=False,
                    text=None,
                    error_type=error_type,
                    records=records,
                )

            except TransientProviderError as exc:
                latency_ms = int((perf_counter() - started) * 1000)
                error_type = type(exc).__name__
                records.append(
                    CallRecord(
                        record_id=str(uuid4()),
                        run_id=run_id,
                        timestamp=datetime.now(UTC),
                        provider="ollama",
                        model_id=self.model_id,
                        task=request.task,
                        case_id=request.case_id,
                        prompt_id=request.prompt_id,
                        prompt_version=request.prompt_version,
                        attempt=attempt,
                        temperature=request.temperature,
                        max_output_tokens=request.max_output_tokens,
                        input_tokens=0,
                        output_tokens=0,
                        cached_input_tokens=None,
                        latency_ms=latency_ms,
                        cost_usd=compute_cost(self.model_id, 0, 0),
                        stop_reason=None,
                        error_type=error_type,
                        response_text=None,
                    )
                )
                if attempt < max_attempts:
                    delay = random.uniform(0, 0.5 * 2 ** (attempt - 1))
                    time.sleep(delay)
                    continue
                return CompletionResult(
                    succeeded=False,
                    text=None,
                    error_type=error_type,
                    records=records,
                )

        return CompletionResult(
            succeeded=False,
            text=None,
            error_type=TransientProviderError.__name__,
            records=records,
        )
