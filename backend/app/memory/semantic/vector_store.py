"""Reads and writes to the `memories` table (SQLAlchemy ORM).

Uses the shared engine from app/db/session.py, one short-lived session per call --
these functions run inside graph nodes, not inside a request-scoped session.

`user_id` stays a plain string at this module's boundary (that's what the graph's
config carries); it's converted to a UUID here, since `memories.user_id` is a real
foreign key to `users`.
"""

import uuid

from sqlalchemy import Text, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import TSQUERY

from app.db.session import session_scope
from app.memory.encoding_gate import EncodingDecision
from app.memory.semantic.embeddings import embed
from app.memory.semantic.models import Memory


def insert_memory(user_id: str, role: str, content: str, decision: EncodingDecision) -> uuid.UUID:
    """Store a message the encoding gate admitted. Returns the new row's id.

    `decision` is the EncodingDecision the gate already computed for this
    message -- its scores are stored alongside the memory rather than
    recomputed, so we always know *why* something was kept.
    """
    memory = Memory(
        user_id=uuid.UUID(user_id),
        role=role,
        content=content,
        embedding=embed(content),
        novelty=decision.novelty,
        salience=decision.salience,
        prediction_error=decision.prediction_error,
        score=decision.score,
    )

    with session_scope() as db:
        db.add(memory)
        db.flush()
        return memory.id


def search_lexical(user_id: str, query: str, limit: int = 10, role: str | None = None) -> list[dict]:
    """L1 -- exact word matches, ranked by cover-density relevance (best first).

    Core Postgres full-text search (`tsvector`/`tsquery`), not pg_search/BM25 --
    Aiven (like every managed Postgres) only allows a curated extension
    allowlist and won't load a custom `shared_preload_libraries` entry, so
    pg_search's BM25 index isn't installable there. `content_tsv` is a STORED
    generated column with a GIN index, so this is still a pure index scan, not
    a per-query re-tokenization.

    `ts_rank_cd` (cover density: rewards matched terms that are close together)
    is the closest core-Postgres analogue to a relevance score. It isn't real
    BM25 -- no document-length normalization -- but it's the standard
    substitute and works fine at this text length. Misses paraphrases entirely
    ("their coursework" won't match "data science") but catches exact rare
    terms the embedding search can blur away -- that's what search_dense is for.

    The query text goes through `plainto_tsquery`, not `to_tsquery`. `to_tsquery`
    parses its argument as its own mini query language (`&`, `|`, `!`, `:*`), so a
    real message containing any of those characters -- an apostrophe in "student's",
    say -- throws a parse error instead of searching for it. `plainto_tsquery` treats
    the text as literal data: punctuation is just a separator, never an operator.
    (`websearch_to_tsquery` looked like the search-box option, but it turns "part-time"
    into a phrase and "-5" into a negation, both wrong for chat text.)

    `plainto_tsquery` ANDs every term, which would require a memory to contain every
    word of a whole chat message and so match almost nothing. The old ParadeDB
    `match()` matched documents containing ANY of the terms, ranked by relevance, so
    the `&` is swapped for `|` to keep that behavior -- `ts_rank_cd` still puts the
    memories covering the most terms first.

    `role` is optional and unfiltered by default -- `ingest_memory`'s
    contradiction check wants nearby memories from either role. Prompt-context
    retrieval (`retrieve()`) passes `role="user"` explicitly instead.
    """
    all_terms = func.plainto_tsquery(literal_column("'english'"), query)
    ts_query = cast(func.replace(cast(all_terms, Text), " & ", " | "), TSQUERY)

    statement = select(Memory.id, Memory.content).where(
        Memory.user_id == uuid.UUID(user_id),
        Memory.content_tsv.op("@@")(ts_query),
    )
    if role is not None:
        statement = statement.where(Memory.role == role)
    statement = statement.order_by(func.ts_rank_cd(Memory.content_tsv, ts_query).desc()).limit(limit)

    with session_scope() as db:
        return [dict(row) for row in db.execute(statement).mappings()]


def search_dense(user_id: str, query: str, limit: int = 10, role: str | None = None) -> list[dict]:
    """L2 -- semantic matches, ranked by cosine distance (closest first).

    `cosine_distance` compiles to pgvector's `<=>` operator (0 = identical direction),
    paired with the `vector_cosine_ops` the HNSW index was built with. Finds
    paraphrases the lexical search would miss, but can dilute an exact rare
    term (a drug name) across 384 dimensions of otherwise-similar text.

    `role` is optional and unfiltered by default -- see search_lexical's
    docstring for why.
    """
    statement = select(Memory.id, Memory.content).where(Memory.user_id == uuid.UUID(user_id))
    if role is not None:
        statement = statement.where(Memory.role == role)
    statement = statement.order_by(Memory.embedding.cosine_distance(embed(query))).limit(limit)

    with session_scope() as db:
        return [dict(row) for row in db.execute(statement).mappings()]
