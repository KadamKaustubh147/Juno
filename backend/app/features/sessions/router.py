import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUserId
from app.dependencies import get_db
from app.features.sessions import service
from app.features.sessions.schemas import MessagesPageOut, SessionListOut, SessionOut
from app.orchestration.checkpointer import checkpointer

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(user_id: CurrentUserId, db: Session = Depends(get_db)):
    """Start a new session. Its `id` is the thread to POST /chat to."""
    created = service.create_session(db, user_id)
    # Commit before responding: get_db's own commit only runs after the response has gone out,
    # and the client can send its first /chat message the moment it has the id.
    db.commit()
    return created


@router.get("", response_model=SessionListOut)
def list_sessions(
    user_id: CurrentUserId,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Sidebar list: this user's sessions, most recently active first."""
    return service.list_sessions(db, user_id, limit)


@router.get("/{session_id}", response_model=SessionOut)
def read_session(session_id: uuid.UUID, user_id: CurrentUserId, db: Session = Depends(get_db)):
    return service.get_session(db, session_id, user_id)


@router.get("/{session_id}/messages", response_model=MessagesPageOut)
def list_messages(
    session_id: uuid.UUID,
    user_id: CurrentUserId,
    before: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Lazy-loaded scrollback: newest page first, older pages via `before`.

    `before` is the id of the oldest message the client currently has; each page is
    the `limit` messages older than it. `has_more` says whether another page exists.
    """
    return service.list_messages(db, session_id, user_id, before, limit)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: uuid.UUID, user_id: CurrentUserId, db: Session = Depends(get_db)):
    """Delete a session, its messages, and the graph's saved conversation state."""
    service.delete_session(db, session_id, user_id)
    db.commit()
    # After the commit, not before: a failure here leaves an orphaned checkpoint nobody can
    # reach, whereas the other order could leave a session whose conversation state is gone.
    checkpointer.delete_thread(str(session_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
