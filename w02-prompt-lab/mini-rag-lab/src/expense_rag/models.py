from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PolicyChunk:
    chunk_id: str
    document: str
    version: str
    section: str
    section_title: str
    text: str
    embedding: list[float] = field(default_factory=list)

    @property
    def section_label(self) -> str:
        return f"{self.section}. {self.section_title}"

    def to_record(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document": self.document,
            "version": self.version,
            "section": self.section,
            "section_title": self.section_title,
            "text": self.text,
            "embedding": self.embedding,
        }


@dataclass
class RetrievedChunk:
    chunk: PolicyChunk
    distance: float

    def to_response(self) -> dict[str, Any]:
        return {
            "section": self.chunk.section_label,
            "distance": float(self.distance),
        }


@dataclass
class Citation:
    document: str
    version: str
    section: str

    def to_response(self) -> dict[str, str]:
        return {
            "document": self.document,
            "version": self.version,
            "section": self.section,
        }


@dataclass
class QueryResponse:
    answer: str
    citation: Optional[Citation]
    retrieved_chunks: list[RetrievedChunk]

    def to_response(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "answer": self.answer,
            "citation": self.citation.to_response() if self.citation else None,
            "retrieved_chunks": [item.to_response() for item in self.retrieved_chunks],
        }
        return payload
