CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_chunks (
    chunk_id TEXT PRIMARY KEY,
    document TEXT NOT NULL,
    version TEXT NOT NULL,
    section TEXT NOT NULL,
    section_title TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding vector(768) NOT NULL
);

CREATE INDEX IF NOT EXISTS policy_chunks_embedding_cosine_idx
    ON policy_chunks
    USING hnsw (embedding vector_cosine_ops);
