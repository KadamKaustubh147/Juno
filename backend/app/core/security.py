"""Current-user extraction for protected routes."""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth.jwt import decode_access_token
from app.core.exceptions import UnauthorizedError
from app.db.session import session_scope
from app.features.users.models import User

# auto_error=False: a missing header would otherwise be a 403; we want 401 like every other auth failure.
_bearer = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    """The authenticated user's id, from the `Authorization: Bearer <jwt>` header.

    Opens its own short session rather than sharing `get_db`'s: a request-scoped session
    would stay open (holding a pooled connection) for as long as a /chat reply streams.
    """
    if credentials is None:
        raise UnauthorizedError("not authenticated")

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise UnauthorizedError("invalid token")

    with session_scope() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("invalid token")

    return user_id


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
