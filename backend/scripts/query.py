"""Ad-hoc retrieval check against whatever's already stored in `memories`.

Doesn't touch the encoding gate or run any conversation -- just calls the same
retrieve() that retrieve_memories (app/orchestration/nodes/memory_hook.py) calls in production, against
data already in Postgres from a previous chat or test_true_memory run.

Run (from the "backend" directory):
    uv run python -m scripts.query <user_id> "<your query>"   (user_id is a users.id UUID)

Defaults to role="user" (matching production prompt-context retrieval) and
limit=5. Pass --all-roles to also see stored assistant replies.
"""

import argparse

from app.memory.retriever import retrieve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id")
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--all-roles", action="store_true", help="don't filter to role=user"
    )
    args = parser.parse_args()

    hits = retrieve(args.user_id, args.query, limit=args.limit, role=None if args.all_roles else "user")

    if not hits:
        print("(no memories retrieved)")
        return

    for rank, hit in enumerate(hits, start=1):
        print(f"{rank}. [{hit['rrf_score']:.4f}] {hit['content']}")


if __name__ == "__main__":
    main()
