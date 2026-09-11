"""Model adapters. Callers use this package, not a vendor response shape."""

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.adapters.ollama import OllamaAdapter

__all__ = [
    "CompletionRequest",
    "CompletionResult",
    "ModelAdapter",
    "OllamaAdapter",
]
