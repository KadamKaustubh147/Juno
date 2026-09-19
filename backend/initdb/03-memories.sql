-- Long-term memory store (ai/memory/store.py). Written to by insert_memory()
-- when the encoding gate (ai/memory/encoding_gate.py) admits a message; read
-- by search_lexical (full-text) and search_dense (pgvector cosine) for
-- retrieval.
--
-- Run by hand against the Aiven service, after 01-extensions.sql:
--   psql "$DATABASE_URL" -f initdb/03-memories.sql
CREATE TABLE IF NOT EXISTS memories (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           TEXT NOT NULL,
    role              TEXT NOT NULL,
    content           TEXT NOT NULL,
    embedding         VECTOR(384),
    -- L1 lexical retrieval (search_lexical in store.py). STORED so it's a
    -- plain column the GIN index scans -- not recomputed per query. No
    -- extension needed, unlike ParadeDB's bm25 index this replaces.
    content_tsv       tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    novelty           REAL NOT NULL,
    salience          REAL NOT NULL,
    prediction_error  REAL NOT NULL,
    score             REAL NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- L2 dense retrieval: nearest-neighbor cosine search (search_dense in store.py).
CREATE INDEX IF NOT EXISTS memories_embedding_hnsw
    ON memories USING hnsw (embedding vector_cosine_ops);

-- L1 lexical retrieval: full-text match + ts_rank_cd ranking (search_lexical in store.py).
CREATE INDEX IF NOT EXISTS memories_content_tsv
    ON memories USING GIN (content_tsv);

CREATE INDEX IF NOT EXISTS memories_user_id ON memories (user_id);
