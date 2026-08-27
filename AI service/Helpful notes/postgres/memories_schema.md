CREATE TABLE memories (
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

CREATE INDEX memories_embedding_hnsw
    ON memories USING hnsw (embedding vector_cosine_ops);

CREATE INDEX memories_content_bm25
    ON memories USING bm25 (id, content)
    WITH (key_field = 'id');

CREATE INDEX memories_user_id ON memories (user_id);
