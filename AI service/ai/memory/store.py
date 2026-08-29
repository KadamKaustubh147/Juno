"""Reads and writes to the `memories` table.

Owns its own connection pool, separate from chatbot.py's -- the memory layer
should work (and be testable) without importing the whole graph.

No `pgvector` Python package here on purpose: psycopg doesn't know how to
convert a VECTOR column on its own, but the fix needs no extra dependency --
format the embedding as a string and let Postgres itself cast it
(`%s::vector`). That package earns its keep in a codebase with vector code
scattered across many files; here it's one write path and two read paths.
"""

import os

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ai.memory.embeddings import embed
from ai.memory.encoding_gate import EncodingDecision

# Loaded here too (chatbot.py also calls this) so this module reads DATABASE_URL
# correctly regardless of import order -- it shouldn't depend on whichever other
# module happens to import it first having already loaded .env. load_dotenv() is
# a no-op if the environment is already populated (e.g. real env vars in prod).
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Return the shared connection pool, opening it on first call."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            max_size=10,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
    return _pool


def _vector_literal(values: list[float]) -> str:
    """Format a Python list the way `::vector` expects to parse it: '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(v) for v in values) + "]"


def insert_memory(user_id: str, role: str, content: str, decision: EncodingDecision) -> str:
    """Store a message the encoding gate admitted. Returns the new row's id.

    `decision` is the EncodingDecision the gate already computed for this
    message -- its scores are stored alongside the memory rather than
    recomputed, so we always know *why* something was kept.
    """
    embedding = _vector_literal(embed(content))

    with get_pool().connection() as conn:
        row = conn.execute(
            """
            INSERT INTO memories
                (user_id, role, content, embedding, novelty, salience, prediction_error, score)
            VALUES
                (%s, %s, %s, %s::vector, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id, role, content, embedding,
                decision.novelty, decision.salience, decision.prediction_error, decision.score,
            ),
        ).fetchone()

    return row["id"]


def search_lexical(user_id: str, query: str, limit: int = 10) -> list[dict]:
    """L1 -- exact word matches, ranked by BM25 relevance (best first).

    `@@@` is pg_search's match operator; `paradedb.score(id)` is its BM25
    score for the row just matched. Misses paraphrases entirely ("their
    coursework" won't match "data science") but catches exact rare terms the
    embedding search can blur away -- that's what search_dense is for.

    The query text is wrapped in `paradedb.match(field, text)` rather than
    passed straight to `@@@`. Bare `@@@ %s` parses its right-hand side as
    pg_search's own query language (colons, quotes, AND/OR are all syntax
    there), so a real message containing any of those characters -- an
    apostrophe in "student's", say -- throws a parse error instead of
    searching for it. `paradedb.match()` treats the text as literal data to
    search for, the way a search box would, not as a mini query to parse.
    """
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, content
            FROM memories
            WHERE user_id = %s AND content @@@ paradedb.match('content', %s)
            ORDER BY paradedb.score(id) DESC
            LIMIT %s
            """,
            (user_id, query, limit),
        ).fetchall()

    return rows


def search_dense(user_id: str, query: str, limit: int = 10) -> list[dict]:
    """L2 -- semantic matches, ranked by cosine distance (closest first).

    `<=>` is pgvector's cosine-distance operator (0 = identical direction),
    paired with the `vector_cosine_ops` the HNSW index was built with. Finds
    paraphrases the lexical search would miss, but can dilute an exact rare
    term (a drug name) across 384 dimensions of otherwise-similar text.
    """
    query_embedding = _vector_literal(embed(query))

    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, content
            FROM memories
            WHERE user_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (user_id, query_embedding, limit),
        ).fetchall()

    return rows
