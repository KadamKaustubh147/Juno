import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    # The session to talk in: the `id` POST /sessions returned. The user comes from the token.
    thread_id: uuid.UUID
    message: str = Field(min_length=1)
