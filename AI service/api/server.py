"""Minimal FastAPI wrapper around the LangGraph chatbot.

Run with (from the "AI service" directory):
    uvicorn api.server:app --reload

Then POST to http://localhost:8000/chat
"""

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ai.chatbot import connection_pool, graph

app = FastAPI(title="AI Therapist Chatbot")


class ChatRequest(BaseModel):
    user_id: str
    message: str
    # thread_id is the chat id
    thread_id: str


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


def stream_reply(request: ChatRequest):
    archive(request.thread_id, request.user_id, "user", request.message)

    reply: list[str] = []
    try:
        thread_id = request.thread_id or request.user_id
        config = {"configurable": {"thread_id": thread_id, "user_id": request.user_id}}
        # stream_mode="messages" yields (chunk, metadata) as the LLM produces tokens, from *any*
        # node that calls the LLM -- including `summarize`, if it runs this turn. We only want
        # to stream the actual reply to the client, so filter to chunks from the "chatbot" node.
        for chunk, metadata in graph.stream(
            {"messages": [{"role": "user", "content": request.message}]},
            config=config,
            stream_mode="messages",
        ):
            if metadata.get("langgraph_node") == "chatbot" and chunk.content:
                reply.append(chunk.content)
                yield chunk.content
    finally:
        # Runs on completion AND on client disconnect / mid-stream crash, so the
        # archive keeps whatever reply text actually made it out.
        text = "".join(reply)
        if text:
            archive(request.thread_id, request.user_id, "assistant", text)


@app.post("/chat")
def chat(request: ChatRequest):
    return StreamingResponse(stream_reply(request), media_type="text/plain")


@app.get("/messages")
def messages(thread_id: str, before: int | None = None, limit: int = Query(default=20, le=50)):
    """Lazy-loaded scrollback: newest page first, older pages via `before`.

    `before` is the smallest message id the client currently has; each page is
    the `limit` rows older than it. `has_more` says whether another page exists.
    """
    with connection_pool.connection() as conn:
        # The pool is created with row_factory=dict_row (a PostgresSaver requirement
        # in chatbot.py), so rows come back as dicts.
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


@app.get("/health")
def health():
    return {"status": "ok"}
