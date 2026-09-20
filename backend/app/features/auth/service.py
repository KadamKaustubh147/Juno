"""Registration and login. Tokens are minted in core/auth/jwt.py; this only checks credentials."""

from sqlalchemy.orm import Session

from app.core.auth.password import hash_password, verify_password
from app.core.exceptions import UnauthorizedError
from app.features.auth.schemas import LoginRequest, RegisterRequest
from app.features.users import service as users_service
from app.features.users.models import User

# Verified against when the email is unknown, so a miss costs the same as a wrong password
# and response time doesn't reveal which emails are registered.
_DUMMY_HASH = hash_password("not-a-real-password")


def register(db: Session, request: RegisterRequest) -> User:
    return users_service.create_user(
        db, request.email, hash_password(request.password), request.full_name
    )


def login(db: Session, request: LoginRequest) -> User:
    user = users_service.get_by_email(db, request.email)
    password_ok = verify_password(request.password, user.hashed_password if user else _DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        raise UnauthorizedError("invalid email or password")
    return user
