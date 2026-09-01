-- Long-term memory store (ai/memory/store.py). Written to by insert_memory()
-- when the encoding gate (ai/memory/encoding_gate.py) admits a message; read
-- by search_lexical (BM25) and search_dense (pgvector cosine) for retrieval.
CREATE TABLE IF NOT EXISTS memories (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           TEXT NOT NULL,
    role              TEXT NOT NULL,
    content           TEXT NOT NULL,
    embedding         VECTOR(384),
    novelty           REAL NOT NULL,
    salience          REAL NOT NULL,
    prediction_error  REAL NOT NULL,
    score             REAL NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- L2 dense retrieval: nearest-neighbor cosine search (search_dense in store.py).
CREATE INDEX IF NOT EXISTS memories_embedding_hnsw
    ON memories USING hnsw (embedding vector_cosine_ops);

-- L1 lexical retrieval: BM25 match (search_lexical in store.py).
CREATE INDEX IF NOT EXISTS memories_content_bm25
    ON memories USING bm25 (id, content)
    WITH (key_field = 'id');

CREATE INDEX IF NOT EXISTS memories_user_id ON memories (user_id);
