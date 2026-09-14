"""Model adapters for the Week 2 local prompt lab."""

from promptlab.adapters.base import CompletionRequest, CompletionResult, ModelAdapter
from promptlab.adapters.ollama import OllamaAdapter

__all__ = [
    "CompletionRequest",
    "CompletionResult",
    "ModelAdapter",
    "OllamaAdapter",
]
