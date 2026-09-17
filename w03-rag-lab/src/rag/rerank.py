"""Reranking. RerankedChunk and the Reranker protocol are shipped complete and
are not modified.

ListwiseReranker is Day 4 work.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:  # pragma: no cover
    from rag.retrieval import RetrievedChunk


class RerankedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    input_rank: int
    output_rank: int
    reason: str


class Reranker(Protocol):
    def rerank(
        self, question: str, candidates: Sequence[RetrievedChunk]
    ) -> list[RerankedChunk]:
        """Return every input candidate, reordered. Never fewer, never more."""
        ...
