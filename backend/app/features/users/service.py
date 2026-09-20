"""User lookups and profile changes. Credentials live in features/auth."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.features.users.models import User


def normalize_email(email: str) -> str:
    """Emails are stored lowercased: the unique index is case-sensitive, so 'A@x.com' and 'a@x.com' would coexist."""
    return email.strip().lower()


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    return user


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def create_user(db: Session, email: str, hashed_password: str, full_name: str | None) -> User:
    if get_by_email(db, email) is not None:
        raise ConflictError("email already registered")

    user = User(email=normalize_email(email), hashed_password=hashed_password, full_name=full_name)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        # Two registrations for the same email raced past the check above; the unique index caught it.
        db.rollback()
        raise ConflictError("email already registered") from None
    return user


def update_profile(db: Session, user_id: uuid.UUID, full_name: str | None) -> User:
    user = get_user(db, user_id)
    user.full_name = full_name
    db.flush()
    return user
