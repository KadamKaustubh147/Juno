from app.features.chat.schemas import ChatRequest
from app.features.sessions.service import archive
from app.orchestration.graph import graph


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
