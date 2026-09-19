"""Sessions logic: therapy sessions, the message archive, and scrollback queries."""

import uuid

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.features.sessions.models import Message, MessageRole, TherapySession
from app.features.users.models import User
from app.shared.constants import DEFAULT_SCRIPT_ID, DEFAULT_SECTION


def ensure_session(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> TherapySession:
    """Return the session with this id, creating it on a thread's first message.

    The id is the thread_id the client generated. A new row gets the interim
    script/section from app/shared/constants.py until the scripts feature sets real ones.
    """
    therapy_session = db.get(TherapySession, session_id)

    if therapy_session is None:
        if db.get(User, user_id) is None:
            raise NotFoundError("user not found")
        therapy_session = TherapySession(
            id=session_id,
            user_id=user_id,
            script_id=DEFAULT_SCRIPT_ID,
            current_section=DEFAULT_SECTION,
        )
        db.add(therapy_session)
        db.flush()
    elif therapy_session.user_id != user_id:
        raise ForbiddenError("session belongs to another user")

    return therapy_session


def archive(db: Session, session_id: uuid.UUID, role: MessageRole, content: str) -> Message:
    """Append one message to the archive.

    The checkpoint prunes old turns when `summarize` fires; this table keeps
    every message verbatim for scrollback. Never read by the graph.
    """
    therapy_session = db.get(TherapySession, session_id)
    if therapy_session is None:
        raise NotFoundError("session not found")

    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        section_at_time=therapy_session.current_section,
    )
    db.add(message)
    db.flush()
    return message


def list_sessions(db: Session, user_id: uuid.UUID) -> dict:
    """Sidebar list: this user's threads, most recently active first."""
    last_at = func.max(Message.created_at)
    rows = db.execute(
        select(TherapySession.id, last_at.label("last_at"))
        .join(Message, Message.session_id == TherapySession.id)
        .where(TherapySession.user_id == user_id)
        .group_by(TherapySession.id)
        .order_by(last_at.desc())
        .limit(50)
    ).all()

    return {
        "sessions": [{"thread_id": str(row.id), "last_at": row.last_at.isoformat()} for row in rows]
    }


def list_messages(
    db: Session, thread_id: uuid.UUID, before: uuid.UUID | None, limit: int
) -> dict:
    """Lazy-loaded scrollback: newest page first, older pages via `before`.

    `before` is the id of the oldest message the client currently has; each page is
    the `limit` messages older than it, ordered by (created_at, id) so ties break
    deterministically. `has_more` says whether another page exists.
    """
    statement = select(Message).where(Message.session_id == thread_id)

    if before is not None:
        cursor = db.get(Message, before)
        if cursor is None or cursor.session_id != thread_id:
            raise NotFoundError("cursor message not found in this thread")
        statement = statement.where(
            tuple_(Message.created_at, Message.id) < tuple_(cursor.created_at, cursor.id)
        )

    rows = db.scalars(
        statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
    ).all()

    return {
        # reverse: DESC query, but clients render chronological
        "messages": [
            {"id": str(row.id), "role": row.role.value, "content": row.content}
            for row in reversed(rows)
        ],
        "has_more": len(rows) == limit,
    }
