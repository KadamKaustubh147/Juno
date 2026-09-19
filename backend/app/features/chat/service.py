from app.db.session import session_scope
from app.features.chat.schemas import ChatRequest
from app.features.sessions import service as sessions_service
from app.features.sessions.models import MessageRole
from app.orchestration.graph import graph


def start_chat(request: ChatRequest) -> None:
    """Validate the user/session and archive the user's message.

    Runs before the response starts streaming, so an unknown user or someone else's
    thread comes back as a proper 404/403 instead of a broken stream.
    """
    with session_scope() as db:
        sessions_service.ensure_session(db, request.thread_id, request.user_id)
        sessions_service.archive(db, request.thread_id, MessageRole.USER, request.message)


def stream_reply(request: ChatRequest):
    reply: list[str] = []
    try:
        config = {
            "configurable": {
                "thread_id": str(request.thread_id),
                "user_id": str(request.user_id),
            }
        }
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
            with session_scope() as db:
                sessions_service.archive(db, request.thread_id, MessageRole.ASSISTANT, text)
