"""Minimal FastAPI wrapper around the LangGraph chatbot.

Run with (from the "AI service" directory):
    uvicorn api.server:app --reload

Then POST to http://localhost:8000/chat
"""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ai.chatbot import graph

app = FastAPI(title="AI Therapist Chatbot")


class ChatRequest(BaseModel):
    user_id: str
    message: str
    # thread_id is the chat id
    thread_id: str


def stream_reply(request: ChatRequest):
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
            yield chunk.content


@app.post("/chat")
def chat(request: ChatRequest):
    return StreamingResponse(stream_reply(request), media_type="text/plain")


@app.get("/health")
def health():
    return {"status": "ok"}
