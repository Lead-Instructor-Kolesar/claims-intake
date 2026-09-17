"""Ingestion. Day 1 work, extended on Day 5.

Reads corpus/manifest.json, parses and chunks every document, embeds embed_text
in batches, creates the index_build row, and inserts chunks against that build.

Day 5 extends this to write the document table alongside the chunk rows and to
emit an IngestionRecord for every source document, including any that produced
no chunks.
"""

from __future__ import annotations


def ingest(build_id: str) -> None:
    """Build an index from corpus source. Day 1 assignment, instruction 5."""
    raise NotImplementedError
