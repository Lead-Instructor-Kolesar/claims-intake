"""Adapter protocol, retry, and budget enforcement. Week 2 reference implementation.

Nothing outside this package imports a provider SDK, references a provider-specific
field name, or branches on which provider is in use. That property is what Days 3
through 5 of Week 2 rely on and it is checkable with a grep.

This layer owns transport retry. It does not own semantic repair, which lives
above it in structured.py. Mixing the two gives you a transport layer that knows
about schemas.
"""

from __future__ import annotations

import json
import random
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from promptlab import config
from promptlab.errors import BudgetExceededError, TransientProviderError
from promptlab.usage import CallRecord, append_record, compute_cost


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: Literal["triage", "summarize", "extract"]
    case_id: str
    prompt_id: str
    prompt_version: str
    system: str
    user_content: str
    temperature: float
    max_output_tokens: int


class CompletionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    succeeded: bool
    text: str | None
    error_type: str | None
    records: list[CallRecord]


class ModelAdapter(Protocol):
    provider: str
    model_id: str

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult: ...


class RawResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int | None
    stop_reason: str | None


def _spend_to_date(run_id: str | None = None) -> float:
    total = 0.0
    for directory in config.SPEND_RECORD_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if run_id is not None and record.get("run_id") != run_id:
                    continue
                total += float(record.get("cost_usd", 0.0) or 0.0)
    return total


class BaseAdapter(ABC):
    """Shared retry, budget, and recording behavior.

    A ceiling that logs a warning and proceeds is not an implementation of the
    budget contract, so a crossing raises and makes no call.
    """

    provider: str
    model_id: str

    def __init__(self, run_dir: Path | None = None) -> None:
        self.run_dir = run_dir or (config.RUN_DIR / "completions")

    @abstractmethod
    def _call(self, request: CompletionRequest) -> RawResponse:
        """Issue one provider call and normalize the response. No retry here."""

    @abstractmethod
    def _classify(self, exc: Exception) -> Exception:
        """Map a provider exception onto the shared error taxonomy."""

    def complete(self, request: CompletionRequest, run_id: str) -> CompletionResult:
        records: list[CallRecord] = []

        for attempt in range(1, config.MAX_ATTEMPTS + 1):
            if _spend_to_date() >= config.SPEND_CEILING_USD:
                raise BudgetExceededError(
                    f"weekly ceiling of {config.SPEND_CEILING_USD:.2f} USD reached"
                )
            if _spend_to_date(run_id) >= config.RUN_CAP_USD:
                raise BudgetExceededError(
                    f"run cap of {config.RUN_CAP_USD:.2f} USD reached for {run_id}"
                )

            started = time.monotonic()
            error: Exception | None = None
            try:
                raw = self._call(request)
            except Exception as exc:
                error = self._classify(exc)
                raw = RawResponse(
                    text=None,
                    input_tokens=0,
                    output_tokens=0,
                    cached_input_tokens=None,
                    stop_reason=None,
                )
            latency_ms = int((time.monotonic() - started) * 1000)

            record = CallRecord(
                run_id=run_id,
                timestamp=datetime.now(UTC),
                provider=self.provider,  # type: ignore[arg-type]
                model_id=self.model_id,
                task=request.task,
                case_id=request.case_id,
                prompt_id=request.prompt_id,
                prompt_version=request.prompt_version,
                attempt=attempt,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
                input_tokens=raw.input_tokens,
                output_tokens=raw.output_tokens,
                cached_input_tokens=raw.cached_input_tokens,
                latency_ms=latency_ms,
                cost_usd=compute_cost(
                    self.model_id,
                    raw.input_tokens,
                    raw.output_tokens,
                    config.PRICING_USD_PER_MTOK,
                ),
                stop_reason=raw.stop_reason,
                error_type=type(error).__name__ if error else None,
                response_text=raw.text,
            )
            records.append(record)
            append_record(record, run_id, self.run_dir)

            if error is None:
                return CompletionResult(
                    succeeded=True, text=raw.text, error_type=None, records=records
                )
            if not isinstance(error, TransientProviderError):
                return CompletionResult(
                    succeeded=False,
                    text=None,
                    error_type=type(error).__name__,
                    records=records,
                )
            if attempt < config.MAX_ATTEMPTS:
                delay = config.BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                time.sleep(delay * (0.5 + random.random()))

        return CompletionResult(
            succeeded=False,
            text=None,
            error_type="TransientProviderError",
            records=records,
        )
