"""Ollama adapter used by every configured local model."""

from __future__ import annotations

import json
import random
import time
from datetime import UTC, datetime
from typing import Any
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

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 180.0
BASE_DELAY_SECONDS = 0.2
MAX_DELAY_SECONDS = 2.0
TRUNCATED_STOP = "length"
_RETRYABLE_STATUS = {408, 409, 425, 429}


def retry_delay(retries_so_far: int) -> float:
    """Equal-jitter backoff. retries_so_far is 1 before the second attempt."""
    scaled = BASE_DELAY_SECONDS * (2 ** (retries_so_far - 1))
    exponent = MAX_DELAY_SECONDS if scaled > MAX_DELAY_SECONDS else scaled
    half = exponent / 2
    return half + random.uniform(0, half)


def attempt_limit() -> int:
    retries = max(0, Settings.from_env().max_retries)
    return min(MAX_ATTEMPTS, 1 + retries)


def classify_status(status: int, message: str) -> Exception:
    detail = message.strip() or f"ollama status {status}"
    if status in _RETRYABLE_STATUS or status >= 500:
        return TransientProviderError(detail)
    return PermanentProviderError(detail)


class OllamaAdapter:
    provider = "ollama"

    def __init__(self, model_id: str, base_url: str | None = None) -> None:
        self.model_id = model_id
        resolved = base_url if base_url is not None else Settings.from_env().ollama_base_url
        self.base_url = resolved.rstrip("/")

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        self._require_known_model()
        records: list[CallRecord] = []
        limit = attempt_limit()

        for attempt in range(1, limit + 1):
            started = time.perf_counter()
            try:
                payload = self._generate(request)
                record = self._record_from_payload(
                    request=request,
                    run_id=run_id,
                    attempt=attempt,
                    latency_ms=_elapsed_ms(started),
                    payload=payload,
                )
            except TransientProviderError as err:
                records.append(
                    self._failure_record(
                        request=request,
                        run_id=run_id,
                        attempt=attempt,
                        latency_ms=_elapsed_ms(started),
                        error=err,
                    )
                )
                if attempt >= limit:
                    return _result(records)
                time.sleep(retry_delay(attempt))
                continue
            except PermanentProviderError as err:
                records.append(
                    self._failure_record(
                        request=request,
                        run_id=run_id,
                        attempt=attempt,
                        latency_ms=_elapsed_ms(started),
                        error=err,
                    )
                )
                return _result(records)

            records.append(record)
            return _result(records)

        return _result(records)

    def _require_known_model(self) -> None:
        known = {config.model_id for config in Settings.from_env().models.values()}
        if self.model_id not in known:
            raise UnknownModelError(self.model_id)

    def _generate(self, request: CompletionRequest) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_id,
                    "prompt": request.user_content,
                    "system": request.system,
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                        "num_predict": request.max_output_tokens,
                    },
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.TransportError as err:
            raise TransientProviderError(str(err)) from err

        status = int(getattr(response, "status_code", 200))
        if status >= 400:
            body = getattr(response, "text", "") or ""
            raise classify_status(status, str(body))

        try:
            payload = response.json()
        except json.JSONDecodeError as err:
            raise TransientProviderError("ollama returned a body that was not json") from err

        if not isinstance(payload, dict):
            raise TransientProviderError("ollama returned a non-object body")
        if "error" in payload and "response" not in payload:
            raise PermanentProviderError(str(payload["error"]))
        return payload

    def _record_from_payload(
        self,
        *,
        request: CompletionRequest,
        run_id: str,
        attempt: int,
        latency_ms: int,
        payload: dict[str, Any],
    ) -> CallRecord:
        try:
            input_tokens = int(payload["prompt_eval_count"])
            output_tokens = int(payload["eval_count"])
        except (KeyError, TypeError, ValueError) as err:
            raise TransientProviderError("ollama omitted token counts") from err

        stop_reason = payload.get("done_reason")
        if stop_reason is not None:
            stop_reason = str(stop_reason)
        response = payload.get("response")
        response_text = None if response is None else str(response)
        error_type = TruncatedResponseError.__name__ if stop_reason == TRUNCATED_STOP else None
        return self._record(
            request=request,
            run_id=run_id,
            attempt=attempt,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=stop_reason,
            error_type=error_type,
            response_text=response_text,
        )

    def _failure_record(
        self,
        *,
        request: CompletionRequest,
        run_id: str,
        attempt: int,
        latency_ms: int,
        error: Exception,
    ) -> CallRecord:
        return self._record(
            request=request,
            run_id=run_id,
            attempt=attempt,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            stop_reason=None,
            error_type=type(error).__name__,
            response_text=None,
        )

    def _record(
        self,
        *,
        request: CompletionRequest,
        run_id: str,
        attempt: int,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
        stop_reason: str | None,
        error_type: str | None,
        response_text: str | None,
    ) -> CallRecord:
        return CallRecord(
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
            error_type=error_type,
            response_text=response_text,
        )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _result(records: list[CallRecord]) -> CompletionResult:
    last = records[-1]
    succeeded = last.error_type is None
    return CompletionResult(
        succeeded=succeeded,
        text=last.response_text,
        error_type=last.error_type,
        records=records,
    )
