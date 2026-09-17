CREATE TABLE index_build (
    build_id                text PRIMARY KEY,
    embedding_model         text        NOT NULL,
    embedding_dimension     integer     NOT NULL,
    chunk_strategy          text        NOT NULL,
    chunk_overlap           integer     NOT NULL,
    corpus_manifest_sha256  text        NOT NULL,
    ingest_git_sha          text        NOT NULL,
    built_at                timestamptz NOT NULL
);

CREATE TABLE chunk (
    chunk_id        text PRIMARY KEY,
    build_id        text    NOT NULL REFERENCES index_build (build_id),
    doc_id          text    NOT NULL,
    version         text    NOT NULL,
    effective_date  date,
    superseded_by   text,
    jurisdiction    text    NOT NULL,
    entity_types    text[]  NOT NULL,
    section         text    NOT NULL,
    section_title   text    NOT NULL,
    ordinal         integer NOT NULL,
    text            text    NOT NULL,
    embed_text      text    NOT NULL,
    text_sha256     text    NOT NULL,
    -- Length rendered from EMBEDDING_DIMENSION. Never typed by hand.
    embedding       vector(1536) NOT NULL
);
