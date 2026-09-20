"""Access-token issuing and verification.

Tokens are HS256 JWTs with the user id as `sub` and deliberately no `exp` -- they never
expire and there are no refresh tokens. The only ways to cut one off are deactivating the
user (`get_current_user_id` checks `is_active` on every request) or rotating JWT_SECRET.
"""

import uuid

import jwt

from app.config import JWT_SECRET

ALGORITHM = "HS256"

if not JWT_SECRET:
    # At import, so the server fails at startup instead of on the first login.
    raise RuntimeError("JWT_SECRET is not set (add it to .env)")


def create_access_token(user_id: uuid.UUID) -> str:
    return jwt.encode({"sub": str(user_id)}, JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    """The user id the token was issued for, or None if it's forged, malformed or has no usable `sub`."""
    try:
        # `algorithms` is pinned so a token can't pick its own (e.g. "none"); no exp is required.
        claims = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM], options={"require": ["sub"]})
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
        return None
