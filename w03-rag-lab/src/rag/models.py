"""Adapter selection. Shipped complete.

Week 3 uses one generation model, pinned in config. This is the only place an
adapter is constructed, so switching provider is a one-line change to
GENERATION_PROVIDER in config.py rather than an edit at every call site.

Call generation_adapter() wherever you need to make a model call. Do not
instantiate an adapter directly.
"""

from __future__ import annotations

from promptlab.adapters.base import ModelAdapter
from rag.config import GENERATION_MODEL, GENERATION_PROVIDER


def generation_adapter() -> ModelAdapter:
    """Return the adapter for the pinned generation model."""
    if GENERATION_PROVIDER == "anthropic":
        from promptlab.adapters.anthropic import AnthropicAdapter

        adapter: ModelAdapter = AnthropicAdapter()
    elif GENERATION_PROVIDER == "azure_openai":
        from promptlab.adapters.azure_openai import AzureOpenAIAdapter

        adapter = AzureOpenAIAdapter()
    else:
        raise ValueError(f"unknown provider {GENERATION_PROVIDER!r}")

    if adapter.model_id != GENERATION_MODEL:
        raise ValueError(
            f"GENERATION_PROVIDER {GENERATION_PROVIDER!r} resolves to model "
            f"{adapter.model_id!r}, but GENERATION_MODEL is {GENERATION_MODEL!r}. "
            "These are set together in rag/config.py."
        )
    return adapter
