ALTER TABLE chunk
    ADD COLUMN text_search tsvector
    GENERATED ALWAYS AS (to_tsvector('english', embed_text)) STORED;

CREATE INDEX chunk_text_search_idx ON chunk USING gin (text_search);
