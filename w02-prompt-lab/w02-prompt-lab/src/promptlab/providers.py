"""Compatibility provider facade for the Week 2 local Ollama lab.

The underlying implementation remains the Day 2 adapter layer.  This module
exists only for code that imports ``OllamaProvider`` / ``CompletionFailed``.
New code should normally use ``promptlab.adapters`` directly.
"""

from __future__ import annotations

from typing import Any

from promptlab.adapters.base import CompletionRequest, CompletionResult
from promptlab.adapters.ollama import OllamaAdapter


class CompletionFailed(RuntimeError):
    """Raised when the delegated Ollama adapter returns an unsuccessful result."""

    def __init__(self, result: CompletionResult) -> None:
        self.result = result
        self.error_type = result.error_type
        self.records = result.records

        message = "Model completion failed"
        if result.error_type:
            message = f"{message}: {result.error_type}"

        super().__init__(message)


class OllamaProvider:
    """Thin compatibility wrapper around the existing ``OllamaAdapter``."""

    provider = "ollama"

    def __init__(self, model_id: str, **adapter_kwargs: Any) -> None:
        self.model_id = model_id
        self._adapter = OllamaAdapter(
            model_id=model_id,
            **adapter_kwargs,
        )

    def complete(
        self,
        request: CompletionRequest,
        run_id: str,
    ) -> CompletionResult:
        """Delegate the call to ``OllamaAdapter``.

        Successful calls return the normal ``CompletionResult``.  Failed
        adapter results are surfaced as ``CompletionFailed`` for compatibility
        with older runner code that expects an exception.
        """

        result = self._adapter.complete(request, run_id)

        if not result.succeeded:
            raise CompletionFailed(result)

        return result

    def __getattr__(self, name: str) -> Any:
        """Delegate any other adapter attributes used by existing code."""
        return getattr(self._adapter, name)
