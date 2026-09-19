"""Sessions logic: the `messages` archive and the queries that read it back for scrollback."""

from app.core.db import connection_pool


def archive(thread_id: str, user_id: str, role: str, content: str):
    """Append one message to the `messages` archive (see initdb/02-messages.sql).

    The checkpoint prunes old turns when `summarize` fires; this table keeps
    every message verbatim for scrollback. Never read by the graph.
    """
    with connection_pool.connection() as conn:
        conn.execute(
            "INSERT INTO messages (thread_id, user_id, role, content) VALUES (%s, %s, %s, %s)",
            (thread_id, user_id, role, content),
        )


def list_sessions(user_id: str) -> dict:
    """Sidebar list: this user's threads, most recently active first."""
    with connection_pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT thread_id, max(created_at) AS last_at
            FROM messages
            WHERE user_id = %s
            GROUP BY thread_id
            ORDER BY last_at DESC
            LIMIT 50
            """,
            (user_id,),
        ).fetchall()

    return {
        "sessions": [
            {"thread_id": r["thread_id"], "last_at": r["last_at"].isoformat()} for r in rows
        ]
    }


def list_messages(thread_id: str, before: int | None, limit: int) -> dict:
    """Lazy-loaded scrollback: newest page first, older pages via `before`.

    `before` is the smallest message id the client currently has; each page is
    the `limit` rows older than it. `has_more` says whether another page exists.
    """
    with connection_pool.connection() as conn:
        # The pool is created with row_factory=dict_row (a PostgresSaver requirement,
        # see app/core/db.py), so rows come back as dicts.
        rows = conn.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE thread_id = %s AND (%s::bigint IS NULL OR id < %s)
            ORDER BY id DESC
            LIMIT %s
            """,
            (thread_id, before, before, limit),
        ).fetchall()

    return {
        # reverse: DESC query, but clients render chronological
        "messages": [
            {"id": row["id"], "role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ],
        "has_more": len(rows) == limit,
    }
