import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.features.sessions import service

router = APIRouter()


@router.get("/sessions")
def sessions(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """Sidebar list: this user's threads, most recently active first."""
    return service.list_sessions(db, user_id)


@router.get("/messages")
def messages(
    thread_id: uuid.UUID,
    before: uuid.UUID | None = None,
    limit: int = Query(default=20, le=50),
    db: Session = Depends(get_db),
):
    """Lazy-loaded scrollback: newest page first, older pages via `before`.

    `before` is the id of the oldest message the client currently has; each page is
    the `limit` messages older than it. `has_more` says whether another page exists.
    """
    return service.list_messages(db, thread_id, before, limit)
