from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str
    message: str
    # thread_id is the chat id
    thread_id: str
