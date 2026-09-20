from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.security import CurrentUserId
from app.features.chat.schemas import ChatRequest
from app.features.chat.service import start_chat, stream_reply

router = APIRouter(tags=["chat"])


@router.post("/chat")
def chat(request: ChatRequest, user_id: CurrentUserId):
    """Send a message; the assistant's reply streams back as Server-Sent Events (see chat/service.py)."""
    user_message_id = start_chat(user_id, request)
    return StreamingResponse(
        stream_reply(user_id, request, user_message_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx: don't buffer the stream
        },
    )
