import uuid

from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: uuid.UUID
    message: str
    # thread_id is the chat id -- it becomes the therapy_sessions.id on the first message.
    thread_id: uuid.UUID
