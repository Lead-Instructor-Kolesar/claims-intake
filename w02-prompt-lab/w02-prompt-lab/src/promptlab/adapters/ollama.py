"""Reusable Ollama adapter for every configured local model."""

from __future__ import annotations

import random
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.config import Settings
from promptlab.errors import (
    PermanentProviderError,
    TransientProviderError,
    TruncatedResponseError,
    UnknownModelError,
)
from promptlab.usage import CallRecord, append_record, compute_cost

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
HTTP_TIMEOUT_SECONDS = 180.0
TRANSIENT_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class OllamaAdapter:
    """One adapter class; Mistral and Qwen differ only by configured model_id."""

    provider: str = "ollama"

    def __init__(self, model_id: str, base_url: str | None = None) -> None:
        settings = Settings.from_env()
        self.model_id = model_id
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._require_configured_model(model_id)

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        records: list[CallRecord] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                payload, latency_ms = self._generate(request)
            except TransientProviderError as exc:
                record = self._failure_record(request, run_id, attempt, 0, type(exc).__name__)
                records.append(record)
                append_record(record, run_id)
                if attempt < MAX_ATTEMPTS:
                    self._backoff(attempt)
                    continue
                return CompletionResult(
                    succeeded=False,
                    text=None,
                    error_type=type(exc).__name__,
                    records=records,
                )
            except PermanentProviderError as exc:
                record = self._failure_record(request, run_id, attempt, 0, type(exc).__name__)
                records.append(record)
                append_record(record, run_id)
                return CompletionResult(
                    succeeded=False,
                    text=None,
                    error_type=type(exc).__name__,
                    records=records,
                )

            text = payload.get("response")
            response_text = str(text) if text is not None else None
            stop_reason = payload.get("done_reason")
            stop_reason_text = str(stop_reason) if stop_reason is not None else None
            input_tokens = int(payload.get("prompt_eval_count") or 0)
            output_tokens = int(payload.get("eval_count") or 0)

            if stop_reason_text == "length":
                error_name = TruncatedResponseError.__name__
                record = self._attempt_record(
                    request=request,
                    run_id=run_id,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    stop_reason=stop_reason_text,
                    error_type=error_name,
                    response_text=response_text,
                )
                records.append(record)
                append_record(record, run_id)
                return CompletionResult(
                    succeeded=False,
                    text=response_text,
                    error_type=error_name,
                    records=records,
                )

            record = self._attempt_record(
                request=request,
                run_id=run_id,
                attempt=attempt,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                stop_reason=stop_reason_text,
                error_type=None,
                response_text=response_text,
            )
            records.append(record)
            append_record(record, run_id)
            return CompletionResult(
                succeeded=True,
                text=response_text,
                error_type=None,
                records=records,
            )

        return CompletionResult(
            succeeded=False,
            text=None,
            error_type="TransientProviderError",
            records=records,
        )

    def _generate(self, request: CompletionRequest) -> tuple[dict[str, Any], int]:
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_id,
                    "system": request.system,
                    "prompt": request.user_content,
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                        "num_predict": request.max_output_tokens,
                    },
                },
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TransientProviderError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise PermanentProviderError(str(exc)) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code in TRANSIENT_STATUS_CODES:
            raise TransientProviderError(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise PermanentProviderError(f"HTTP {response.status_code}")

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise PermanentProviderError("malformed Ollama response") from exc

        if payload.get("error"):
            raise PermanentProviderError(str(payload["error"]))
        return payload, latency_ms

    def _backoff(self, attempt: int) -> None:
        delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
        time.sleep(delay + random.uniform(0.0, BACKOFF_BASE_SECONDS))

    def _failure_record(
        self,
        request: CompletionRequest,
        run_id: str,
        attempt: int,
        latency_ms: int,
        error_type: str,
    ) -> CallRecord:
        return self._attempt_record(
            request=request,
            run_id=run_id,
            attempt=attempt,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            stop_reason=None,
            error_type=error_type,
            response_text=None,
        )

    def _attempt_record(
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
            stop_reason=stop_reason,
            error_type=error_type,
            response_text=response_text,
        )

    @staticmethod
    def _require_configured_model(model_id: str) -> None:
        settings = Settings.from_env()
        configured = {model.model_id for model in settings.models.values()}
        if model_id not in configured:
            raise UnknownModelError(model_id)
