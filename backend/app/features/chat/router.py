from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.features.chat.schemas import ChatRequest
from app.features.chat.service import start_chat, stream_reply

router = APIRouter()


@router.post("/chat")
def chat(request: ChatRequest):
    start_chat(request)
    return StreamingResponse(stream_reply(request), media_type="text/plain")
