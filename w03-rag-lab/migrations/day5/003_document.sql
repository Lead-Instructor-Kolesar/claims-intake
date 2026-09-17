CREATE TABLE document (
    build_id        text    NOT NULL REFERENCES index_build (build_id),
    doc_id          text    NOT NULL,
    version         text    NOT NULL,
    title           text    NOT NULL,
    family          text    NOT NULL,
    effective_date  date,
    superseded_by   text,
    jurisdiction    text    NOT NULL,
    entity_types    text[]  NOT NULL,
    source_path     text    NOT NULL,
    source_sha256   text    NOT NULL,
    PRIMARY KEY (build_id, doc_id, version)
);

ALTER TABLE chunk
    ADD CONSTRAINT chunk_document_fk
    FOREIGN KEY (build_id, doc_id, version)
    REFERENCES document (build_id, doc_id, version);
