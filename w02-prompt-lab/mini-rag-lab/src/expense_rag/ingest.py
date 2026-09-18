from __future__ import annotations

from expense_rag.config import Settings
from expense_rag.db import apply_schema, connect, count_chunks, replace_chunks
from expense_rag.chunking import chunk_policy
from expense_rag.models import PolicyChunk
from expense_rag.ollama_client import OllamaClient


def ingest_policy(settings: Settings) -> list[PolicyChunk]:
    markdown = settings.policy_path.read_text(encoding="utf-8")
    chunks = chunk_policy(markdown)
    client = OllamaClient(settings)

    for chunk in chunks:
        chunk.embedding = client.embed_document(chunk.text)

    with connect(settings) as conn:
        apply_schema(conn, settings)
        replace_chunks(conn, chunks)
        stored = count_chunks(conn)

    if stored != 6:
        raise RuntimeError(f"Ingest stored {stored} chunks, expected 6")
    return chunks
