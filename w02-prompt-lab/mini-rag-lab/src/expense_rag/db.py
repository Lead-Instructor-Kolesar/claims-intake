from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from expense_rag.config import Settings
from expense_rag.models import PolicyChunk, RetrievedChunk


@contextmanager
def connect(settings: Settings) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    register_vector(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_schema(conn: psycopg.Connection, settings: Settings) -> None:
    sql = settings.migration_path.read_text(encoding="utf-8")
    conn.execute(sql)


def replace_chunks(conn: psycopg.Connection, chunks: list[PolicyChunk]) -> None:
    conn.execute("DELETE FROM policy_chunks")
    with conn.cursor() as cur:
        for chunk in chunks:
            cur.execute(
                """
                INSERT INTO policy_chunks (
                    chunk_id, document, version, section, section_title, text, embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    chunk.chunk_id,
                    chunk.document,
                    chunk.version,
                    chunk.section,
                    chunk.section_title,
                    chunk.text,
                    chunk.embedding,
                ),
            )


def count_chunks(conn: psycopg.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM policy_chunks").fetchone()
    return int(row["n"]) if row else 0


def retrieve_chunks(
    conn: psycopg.Connection,
    query_embedding: list[float],
    limit: int = 3,
) -> list[RetrievedChunk]:
    rows = conn.execute(
        """
        SELECT
            chunk_id,
            document,
            version,
            section,
            section_title,
            text,
            embedding <=> %s::vector AS distance
        FROM policy_chunks
        ORDER BY embedding <=> %s::vector ASC
        LIMIT %s
        """,
        (query_embedding, query_embedding, limit),
    ).fetchall()

    results: list[RetrievedChunk] = []
    for row in rows:
        chunk = PolicyChunk(
            chunk_id=row["chunk_id"],
            document=row["document"],
            version=row["version"],
            section=row["section"],
            section_title=row["section_title"],
            text=row["text"],
        )
        results.append(RetrievedChunk(chunk=chunk, distance=float(row["distance"])))
    return results
