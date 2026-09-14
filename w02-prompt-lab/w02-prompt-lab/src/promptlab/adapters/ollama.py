from __future__ import annotations

import random
import time
import uuid
from datetime import UTC, datetime
from typing import Any, cast

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

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_JITTER_SECONDS = 0.1
REQUEST_TIMEOUT_SECONDS = 300.0


class OllamaAdapter:
    provider = "ollama"

    def __init__(self, model_id: str) -> None:
        settings = Settings.from_env()
        configured_ids = {config.model_id for config in settings.models.values()}
        if model_id not in configured_ids:
            raise UnknownModelError(f"Unknown model identifier: {model_id}")
        self.model_id = model_id
        self._base_url = settings.ollama_base_url

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        records: list[CallRecord] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            payload, latency_ms, error = self._attempt(request)
            error_type = type(error).__name__ if error is not None else None
            response_text = response_text_from(payload) if payload is not None else None
            records.append(
                self._record(
                    request=request,
                    run_id=run_id,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    payload=payload,
                    error_type=error_type,
                    response_text=response_text,
                )
            )
            if error is None:
                return CompletionResult(
                    succeeded=True,
                    text=response_text,
                    error_type=None,
                    records=records,
                )
            if isinstance(error, TransientProviderError) and attempt < MAX_ATTEMPTS:
                time.sleep(backoff_seconds(attempt))
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

    def _attempt(
        self,
        request: CompletionRequest,
    ) -> tuple[dict[str, Any] | None, int, Exception | None]:
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self.model_id,
                    "prompt": f"{request.system}\n\n{request.user_content}",
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                        "num_predict": request.max_output_tokens,
                    },
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            latency_ms = elapsed_ms(started)
            return None, latency_ms, TransientProviderError(str(exc))
        latency_ms = elapsed_ms(started)
        status_error = classify_status(response.status_code)
        if status_error is not None:
            return None, latency_ms, status_error
        payload = json_object(response)
        if payload is None:
            return None, latency_ms, PermanentProviderError("Ollama did not return a JSON object")
        if optional_str(payload.get("done_reason")) == "length":
            return payload, latency_ms, TruncatedResponseError(
                "Ollama reached the output token ceiling"
            )
        return payload, latency_ms, None

    def _record(
        self,
        *,
        request: CompletionRequest,
        run_id: str,
        attempt: int,
        latency_ms: int,
        payload: dict[str, Any] | None,
        error_type: str | None,
        response_text: str | None,
    ) -> CallRecord:
        input_tokens = token_count(payload, "prompt_eval_count")
        output_tokens = token_count(payload, "eval_count")
        return CallRecord(
            record_id=str(uuid.uuid4()),
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
            stop_reason=optional_str(payload.get("done_reason")) if payload else None,
            error_type=error_type,
            response_text=response_text,
        )


def backoff_seconds(attempt: int) -> float:
    delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
    jitter = random.random() * BACKOFF_JITTER_SECONDS
    return cast(float, delay + jitter)


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def classify_status(status_code: int) -> Exception | None:
    if status_code == 429 or status_code >= 500:
        return TransientProviderError(f"Temporary provider status {status_code}")
    if status_code >= 400:
        return PermanentProviderError(f"Non-retryable provider status {status_code}")
    return None


def json_object(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload: Any = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def token_count(payload: dict[str, Any] | None, key: str) -> int:
    if payload is None:
        return 0
    value = payload.get(key)
    return value if isinstance(value, int) else 0


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def response_text_from(payload: dict[str, Any]) -> str | None:
    response = payload.get("response")
    if isinstance(response, str):
        return response
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return None
