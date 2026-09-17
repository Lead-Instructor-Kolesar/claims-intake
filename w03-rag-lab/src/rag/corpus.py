"""Corpus models. Shipped complete. Associates do not modify DocumentMeta or Chunk.

`chunk_document` is Day 1 work.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

Family = Literal["kyc_periodic_review", "card_dispute_procedure", "compliance_manual"]


class DocumentMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    title: str
    family: Family
    version: str
    effective_date: date | None
    superseded_by: str | None
    jurisdiction: str
    entity_types: list[str]
    source_path: str
    source_sha256: str


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_id: str
    version: str
    effective_date: date | None
    superseded_by: str | None
    jurisdiction: str
    entity_types: list[str]
    section: str
    section_title: str
    ordinal: int
    text: str
    embed_text: str
    text_sha256: str


def chunk_document(meta: DocumentMeta, body: str) -> list[Chunk]:
    """Split a document body into chunks on its numbered section structure.

    Sections longer than CHUNK_MAX_CHARS are subdivided, with CHUNK_OVERLAP_CHARS
    applied at the internal boundaries and nowhere else. `embed_text` carries the
    document title, version, and section heading; `text` is the section text
    unmodified. `chunk_id` is doc_id:version:section:ordinal.

    Day 1 assignment, instruction 2.
    """
    raise NotImplementedError
