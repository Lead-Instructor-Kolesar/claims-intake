"""Store access. Shipped complete.

Writing rows is plumbing and is not what any day of this week assesses. Note that
nothing here offers an update or a delete. The index is derived from
corpus/source/, a rebuild is the routine operation, and a hand-patched row is a
fact about the system that exists nowhere in source.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg
from pgvector.psycopg import register_vector

from rag.config import (
    CHUNK_OVERLAP_CHARS,
    CHUNK_STRATEGY,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    database_url,
)
from rag.corpus import Chunk


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """Open a connection with the vector type registered."""
    conn = psycopg.connect(database_url())
    try:
        register_vector(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_build(
    conn: psycopg.Connection,
    build_id: str,
    corpus_manifest_sha256: str,
    ingest_git_sha: str,
) -> None:
    """Record the identity of an index build.

    Rows carry the build they came from, so two builds coexist in one table and
    can be compared by query. That comparison is the only evidence available
    that a loader fix worked.
    """
    conn.execute(
        """
        INSERT INTO index_build (
            build_id, embedding_model, embedding_dimension, chunk_strategy,
            chunk_overlap, corpus_manifest_sha256, ingest_git_sha, built_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            build_id,
            EMBEDDING_MODEL,
            EMBEDDING_DIMENSION,
            CHUNK_STRATEGY,
            CHUNK_OVERLAP_CHARS,
            corpus_manifest_sha256,
            ingest_git_sha,
            datetime.now(UTC),
        ),
    )


def insert_chunks(
    conn: psycopg.Connection,
    build_id: str,
    chunks: Sequence[Chunk],
    embeddings: Sequence[Sequence[float]],
) -> int:
    """Insert chunks against a build. Returns the number of rows written.

    chunk_id is the primary key and is derived from document properties, so
    re-ingesting unchanged content updates rows rather than accumulating
    duplicates.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"{len(chunks)} chunks and {len(embeddings)} embeddings; these must match"
        )
    for vector in embeddings:
        if len(vector) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"embedding of length {len(vector)}; EMBEDDING_DIMENSION is "
                f"{EMBEDDING_DIMENSION}"
            )
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunk (
                chunk_id, build_id, doc_id, version, effective_date, superseded_by,
                jurisdiction, entity_types, section, section_title, ordinal,
                text, embed_text, text_sha256, embedding
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id) DO UPDATE SET
                build_id = EXCLUDED.build_id,
                text = EXCLUDED.text,
                embed_text = EXCLUDED.embed_text,
                text_sha256 = EXCLUDED.text_sha256,
                embedding = EXCLUDED.embedding
            """,
            [
                (
                    c.chunk_id, build_id, c.doc_id, c.version, c.effective_date,
                    c.superseded_by, c.jurisdiction, c.entity_types, c.section,
                    c.section_title, c.ordinal, c.text, c.embed_text, c.text_sha256,
                    list(v),
                )
                for c, v in zip(chunks, embeddings, strict=True)
            ],
        )
    return len(chunks)
