"""Day 5 contract. Exercises the ingestion record shape against fixtures, with no
database access.

IngestionRecord is Day 5 work, so these fail until it exists. That is intended.
"""

from __future__ import annotations

import pytest

REQUIRED_FIELDS = {
    "build_id",
    "source_path",
    "source_sha256",
    "reader",
    "null_fields",
    "chunk_count",
    "ingest_git_sha",
}


def _record_model() -> type:
    from rag import lineage

    model = getattr(lineage, "IngestionRecord", None)
    if model is None:
        pytest.fail("IngestionRecord is not defined in rag.lineage")
    return model


def test_ingestion_record_carries_every_required_field() -> None:
    model = _record_model()
    assert set(model.model_fields) >= REQUIRED_FIELDS


def test_ingestion_record_can_describe_a_document_that_produced_nothing() -> None:
    model = _record_model()
    record = model(
        build_id="b1",
        source_path="corpus/source/cmp-ie-0021-v1.4.md",
        source_sha256="0" * 64,
        reader="document_control_table",
        null_fields=["effective_date"],
        chunk_count=0,
        ingest_git_sha="abc1234",
    )
    assert record.chunk_count == 0
