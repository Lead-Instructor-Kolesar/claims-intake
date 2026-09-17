"""Anthropic adapter. Week 2 reference implementation.

Provider field names are mapped onto CallRecord here and nowhere else.
"""

from __future__ import annotations

import os
from pathlib import Path

import anthropic

from promptlab import config
from promptlab.adapters.base import BaseAdapter, CompletionRequest, RawResponse
from promptlab.errors import (
    PermanentProviderError,
    TransientProviderError,
    TruncatedResponseError,
)


class AnthropicAdapter(BaseAdapter):
    provider = "anthropic"

    def __init__(self, run_dir: Path | None = None) -> None:
        super().__init__(run_dir)
        self.model_id = config.MODELS["anthropic"]
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def _call(self, request: CompletionRequest) -> RawResponse:
        response = self._client.messages.create(
            model=self.model_id,
            system=request.system,
            messages=[{"role": "user", "content": request.user_content}],
            temperature=request.temperature,
            max_tokens=request.max_output_tokens,
        )
        if response.stop_reason == "max_tokens":
            raise TruncatedResponseError(
                f"output ceiling of {request.max_output_tokens} reached"
            )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        usage = response.usage
        return RawResponse(
            text=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=getattr(usage, "cache_read_input_tokens", None),
            stop_reason=response.stop_reason,
        )

    def _classify(self, exc: Exception) -> Exception:
        if isinstance(exc, TruncatedResponseError):
            return exc
        if isinstance(
            exc,
            anthropic.RateLimitError
            | anthropic.APITimeoutError
            | anthropic.APIConnectionError
            | anthropic.InternalServerError,
        ):
            return TransientProviderError(str(exc))
        if isinstance(exc, anthropic.APIStatusError):
            return PermanentProviderError(str(exc))
        return PermanentProviderError(str(exc))
