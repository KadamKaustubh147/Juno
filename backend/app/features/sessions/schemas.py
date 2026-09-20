import uuid
from datetime import datetime

from pydantic import BaseModel

from app.features.sessions.models import MessageRole, SessionStatus


class SessionOut(BaseModel):
    id: uuid.UUID
    status: SessionStatus
    script_id: str
    # "Section 1".."Section 8" once the graph has run; the section a new session starts in before that.
    current_section: str
    created_at: datetime
    ended_at: datetime | None
    # Latest message, or created_at for a session nobody has written in yet.
    last_at: datetime


class SessionListOut(BaseModel):
    sessions: list[SessionOut]


class MessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime


class MessagesPageOut(BaseModel):
    messages: list[MessageOut]
    has_more: bool
