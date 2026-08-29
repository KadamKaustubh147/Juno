-- Archive of every chat message, verbatim, forever.
-- The LangGraph checkpoint prunes old turns when `summarize` runs; this table
-- is what scrollback (GET /messages) reads from. Never read by the LLM.
CREATE TABLE IF NOT EXISTS messages (
    id         BIGSERIAL PRIMARY KEY,
    thread_id  TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cursor pagination is WHERE thread_id = ? AND id < ? ORDER BY id DESC
CREATE INDEX IF NOT EXISTS messages_thread_id_id ON messages (thread_id, id);
