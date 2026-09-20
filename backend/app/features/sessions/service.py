"""Sessions logic: therapy sessions, the message archive, and scrollback queries.

Every function that takes a `user_id` only ever touches that user's sessions; someone else's
session id looks exactly like one that doesn't exist (404).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, func, select, tuple_
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.features.sessions.models import (
    Message,
    MessageRole,
    SectionTransition,
    SessionStatus,
    TherapySession,
)
from app.features.sessions.schemas import (
    MessageOut,
    MessagesPageOut,
    SessionListOut,
    SessionOut,
)
from app.orchestration.script_loader import FIRST_SECTION
from app.shared.constants import DEFAULT_SCRIPT_ID


def create_session(db: Session, user_id: uuid.UUID) -> SessionOut:
    """Start a new session at the script's first section."""
    therapy_session = TherapySession(
        user_id=user_id, script_id=DEFAULT_SCRIPT_ID, current_section=FIRST_SECTION
    )
    db.add(therapy_session)
    db.flush()
    db.refresh(therapy_session)  # created_at is a server default
    return _to_out(therapy_session, therapy_session.created_at)


def get_owned(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> TherapySession:
    """The session, or NotFoundError if it doesn't exist *or* belongs to someone else."""
    therapy_session = db.get(TherapySession, session_id)
    if therapy_session is None or therapy_session.user_id != user_id:
        raise NotFoundError("session not found")
    return therapy_session


def get_session(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> SessionOut:
    row = db.execute(
        _sessions_with_last_at().where(
            TherapySession.id == session_id, TherapySession.user_id == user_id
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("session not found")
    return _to_out(*row)


def list_sessions(db: Session, user_id: uuid.UUID, limit: int) -> SessionListOut:
    """Sidebar list: this user's sessions, most recently active first."""
    rows = db.execute(
        _sessions_with_last_at()
        .where(TherapySession.user_id == user_id)
        .order_by(desc("last_at"))
        .limit(limit)
    ).all()
    return SessionListOut(sessions=[_to_out(*row) for row in rows])


def delete_session(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Delete the session row; its messages and transitions go with it (ON DELETE CASCADE).

    The LangGraph checkpoint for the thread is separate -- the caller drops it once this commits.
    """
    db.delete(get_owned(db, session_id, user_id))
    db.flush()


def archive(
    db: Session,
    session_id: uuid.UUID,
    role: MessageRole,
    content: str,
    section: str | None = None,
) -> Message:
    """Append one message to the archive.

    The checkpoint prunes old turns when `summarize` fires; this table keeps
    every message verbatim for scrollback. Never read by the graph. `section` is the section
    the message belongs to; it defaults to the session's current one.
    """
    therapy_session = db.get(TherapySession, session_id)
    if therapy_session is None:
        raise NotFoundError("session not found")

    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        section_at_time=section or therapy_session.current_section,
    )
    db.add(message)
    db.flush()
    return message


def record_progress(
    db: Session,
    session_id: uuid.UUID,
    current_section: str | None,
    transitions: list[dict],
    session_done: bool,
) -> str:
    """Copy the graph's progress (from its checkpoint) onto the session row; returns the session's current section.

    A `current_section` of None (nothing in the checkpoint yet) leaves the row's section alone.

    `transitions` is the checkpoint's full history, which only ever grows, so the ones not
    yet in `section_transitions` are exactly the tail past the rows already there. That makes
    this safe to call again after a turn that was cut short.
    """
    therapy_session = db.get(TherapySession, session_id)
    if therapy_session is None:
        raise NotFoundError("session not found")

    if current_section is not None:
        therapy_session.current_section = current_section

    recorded = db.scalar(
        select(func.count())
        .select_from(SectionTransition)
        .where(SectionTransition.session_id == session_id)
    )
    for transition in transitions[recorded:]:
        db.add(
            SectionTransition(
                session_id=session_id,
                from_section=transition["from"],
                to_section=transition["to"],
                reasoning=transition.get("reasoning"),
            )
        )

    if session_done and therapy_session.status == SessionStatus.ACTIVE:
        therapy_session.status = SessionStatus.COMPLETED
        therapy_session.ended_at = datetime.now(UTC)
    db.flush()
    return therapy_session.current_section


def list_messages(
    db: Session, session_id: uuid.UUID, user_id: uuid.UUID, before: uuid.UUID | None, limit: int
) -> MessagesPageOut:
    """Lazy-loaded scrollback: newest page first, older pages via `before`.

    `before` is the id of the oldest message the client currently has; each page is
    the `limit` messages older than it, ordered by (created_at, id) so ties break
    deterministically. `has_more` says whether another page exists.
    """
    get_owned(db, session_id, user_id)
    statement = select(Message).where(Message.session_id == session_id)

    if before is not None:
        cursor = db.get(Message, before)
        if cursor is None or cursor.session_id != session_id:
            raise NotFoundError("cursor message not found in this session")
        statement = statement.where(
            tuple_(Message.created_at, Message.id) < tuple_(cursor.created_at, cursor.id)
        )

    # One row past the page, only to learn whether there is another page.
    rows = db.scalars(
        statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)
    ).all()

    return MessagesPageOut(
        # reverse: DESC query, but clients render chronological
        messages=[
            MessageOut(id=row.id, role=row.role, content=row.content, created_at=row.created_at)
            for row in reversed(rows[:limit])
        ],
        has_more=len(rows) > limit,
    )


def _sessions_with_last_at():
    """Select (TherapySession, last_at) with the session's latest message time, or its creation time if empty."""
    last_at = func.coalesce(func.max(Message.created_at), TherapySession.created_at)
    return (
        select(TherapySession, last_at.label("last_at"))
        .outerjoin(Message, Message.session_id == TherapySession.id)
        .group_by(TherapySession.id)
    )


def _to_out(therapy_session: TherapySession, last_at: datetime) -> SessionOut:
    return SessionOut(
        id=therapy_session.id,
        status=therapy_session.status,
        script_id=therapy_session.script_id,
        current_section=therapy_session.current_section,
        created_at=therapy_session.created_at,
        ended_at=therapy_session.ended_at,
        last_at=last_at,
    )
