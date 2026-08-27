"""Retrieval -- fuses L1 (lexical) and L2 (dense) search into one ranking.

    RRF(memory) = sum over each list the memory appears in:  1 / (k + rank)

k=60 is the constant from the original paper (Cormack et al., 2009); everyone
just uses it. It flattens the gap between top ranks, so being first in one
list doesn't automatically outrank appearing in both lists lower down --
consensus between L1 and L2 matters more than topping either alone.

Runs in Python, not SQL: both searches already do their real work as index
scans inside Postgres (BM25, HNSW) and hand back small ranked lists (~10-20
rows each). Summing 1/(k+rank) over that many rows costs nothing wherever it
runs, so it's kept in Python for the same reason encoding_gate.py's logic is
plain Python rather than a stored procedure -- easy to unit-test with
fabricated rankings, no database required.
"""

from ai.memory.store import search_dense, search_lexical

RRF_K = 60


def rrf_fuse(ranked_id_lists: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Merge several ranked id lists (best first) into one ranking.

    Returns (id, rrf_score) pairs sorted best-first. Takes plain lists of ids,
    not search results directly, so this can be tested with made-up rankings
    and no database.
    """
    scores: dict[str, float] = {}

    for ranked_ids in ranked_id_lists:
        for rank, memory_id in enumerate(ranked_ids, start=1):
            scores[memory_id] = scores.get(memory_id, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def retrieve(user_id: str, query: str, limit: int = 10) -> list[dict]:
    """Retrieve the memories most relevant to `query` for this user.

    Runs L1 and L2 in parallel-ish (one after another, both fast), fuses their
    rankings with RRF, then looks the winning ids back up against whichever
    search result already had their content -- no extra DB round trip needed
    for that, since both searches already returned (id, content) rows.
    """
    lexical_hits = search_lexical(user_id, query, limit=limit)
    dense_hits = search_dense(user_id, query, limit=limit)

    # id -> content, from whichever search saw it first. Built once so the
    # fused list below doesn't need a third query just to fetch text back.
    content_by_id = {row["id"]: row["content"] for row in lexical_hits + dense_hits}

    fused = rrf_fuse([
        [row["id"] for row in lexical_hits],
        [row["id"] for row in dense_hits],
    ])

    return [
        {"id": memory_id, "content": content_by_id[memory_id], "rrf_score": score}
        for memory_id, score in fused[:limit]
    ]
