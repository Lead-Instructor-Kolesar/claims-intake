"""Embedding adapter. Day 1 work.

Define the EmbeddingAdapter protocol and EmbeddingCallRecord here, then implement
embed_texts against the Azure OpenAI embeddings deployment named in the
environment. Batch the requests, and assert the returned vector length against
EMBEDDING_DIMENSION before anything is inserted.

EmbeddingCallRecord carries run_id, call_id, model, input_tokens, vector_count,
cost_usd, latency_ms, started_at, and error_type. Every call writes one,
including failures.
"""

from __future__ import annotations


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings. Day 1 assignment, instruction 3."""
    raise NotImplementedError
