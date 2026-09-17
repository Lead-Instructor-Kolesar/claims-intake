"""Azure OpenAI adapter. Week 2 reference implementation.

Its usage fields and finish reason are named differently from Anthropic's and are
mapped onto the same unchanged CallRecord. The mapping is the point; widening
CallRecord to accommodate both shapes would defeat it.

Associates create their own Azure deployments, so the deployment name is read
from the environment rather than pinned.
"""

from __future__ import annotations

import os
from pathlib import Path

import openai

from promptlab import config
from promptlab.adapters.base import BaseAdapter, CompletionRequest, RawResponse
from promptlab.errors import (
    PermanentProviderError,
    TransientProviderError,
    TruncatedResponseError,
)


class AzureOpenAIAdapter(BaseAdapter):
    provider = "azure_openai"

    def __init__(self, run_dir: Path | None = None) -> None:
        super().__init__(run_dir)
        self.model_id = config.MODELS["azure_openai"]
        self._deployment = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]
        self._client = openai.AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        )

    def _call(self, request: CompletionRequest) -> RawResponse:
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user_content},
            ],
            temperature=request.temperature,
            max_completion_tokens=request.max_output_tokens,
        )
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise TruncatedResponseError(
                f"output ceiling of {request.max_output_tokens} reached"
            )
        usage = response.usage
        cached = None
        if usage is not None and usage.prompt_tokens_details is not None:
            cached = usage.prompt_tokens_details.cached_tokens
        return RawResponse(
            text=choice.message.content,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cached_input_tokens=cached,
            stop_reason=choice.finish_reason,
        )

    def _classify(self, exc: Exception) -> Exception:
        if isinstance(exc, TruncatedResponseError):
            return exc
        if isinstance(
            exc,
            openai.RateLimitError
            | openai.APITimeoutError
            | openai.APIConnectionError
            | openai.InternalServerError,
        ):
            return TransientProviderError(str(exc))
        return PermanentProviderError(str(exc))
