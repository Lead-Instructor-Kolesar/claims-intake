"""Day 1 contract. Exercises chunk identifier construction and metadata
propagation against a fixture document, with no database and no network access.

These fail until chunk_document is implemented. That is intended.
"""

from __future__ import annotations

from rag.config import CHUNK_MAX_CHARS
from rag.corpus import DocumentMeta, chunk_document


def test_chunk_id_is_derived_from_document_properties(
    fixture_meta: DocumentMeta, fixture_body: str
) -> None:
    chunks = chunk_document(fixture_meta, fixture_body)
    for chunk in chunks:
        expected = f"{chunk.doc_id}:{chunk.version}:{chunk.section}:{chunk.ordinal}"
        assert chunk.chunk_id == expected


def test_chunk_ids_are_stable_across_runs(
    fixture_meta: DocumentMeta, fixture_body: str
) -> None:
    first = {c.chunk_id for c in chunk_document(fixture_meta, fixture_body)}
    second = {c.chunk_id for c in chunk_document(fixture_meta, fixture_body)}
    assert first == second


def test_metadata_is_present_on_every_chunk_row(
    fixture_meta: DocumentMeta, fixture_body: str
) -> None:
    for chunk in chunk_document(fixture_meta, fixture_body):
        assert chunk.version == fixture_meta.version
        assert chunk.effective_date == fixture_meta.effective_date
        assert chunk.superseded_by == fixture_meta.superseded_by
        assert chunk.jurisdiction == fixture_meta.jurisdiction
        assert chunk.entity_types == fixture_meta.entity_types


def test_text_is_citable_and_embed_text_carries_the_heading(
    fixture_meta: DocumentMeta, fixture_body: str
) -> None:
    for chunk in chunk_document(fixture_meta, fixture_body):
        assert chunk.section
        assert chunk.section_title
        assert chunk.section_title in chunk.embed_text
        assert chunk.section_title not in chunk.text
        assert chunk.text in fixture_body


def test_no_chunk_spans_two_sections(
    fixture_meta: DocumentMeta, fixture_body: str
) -> None:
    chunks = chunk_document(fixture_meta, fixture_body)
    sections = [c.section for c in chunks]
    assert len(sections) == len(chunks)
    for chunk in chunks:
        assert len(chunk.text) <= CHUNK_MAX_CHARS or chunk.ordinal >= 0
