from fastapi import APIRouter, Query

from app.features.sessions import service

router = APIRouter()


@router.get("/sessions")
def sessions(user_id: str):
    """Sidebar list: this user's threads, most recently active first."""
    return service.list_sessions(user_id)


@router.get("/messages")
def messages(thread_id: str, before: int | None = None, limit: int = Query(default=20, le=50)):
    """Lazy-loaded scrollback: newest page first, older pages via `before`.

    `before` is the smallest message id the client currently has; each page is
    the `limit` rows older than it. `has_more` says whether another page exists.
    """
    return service.list_messages(thread_id, before, limit)
