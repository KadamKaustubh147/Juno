"""Create the interim dev user (there's no auth/registration yet).

Run (from the "backend" directory, after `alembic upgrade head`):
    uv run python -m scripts.seed_dev_user

The frontend's USER_ID (frontend/src/App.tsx) is this fixed UUID. hashed_password is '!',
which is not a valid hash, so nobody can log in as this user -- real auth replaces this.
"""

import uuid

from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.features.users.models import User

DEV_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def ensure_user(db: Session, user_id: uuid.UUID, email: str, full_name: str | None = None) -> User:
    user = db.get(User, user_id)
    if user is None:
        user = User(id=user_id, email=email, hashed_password="!", full_name=full_name)
        db.add(user)
        db.flush()
    return user


if __name__ == "__main__":
    with session_scope() as db:
        ensure_user(db, DEV_USER_ID, "dev@juno.local", "Dev User")
    print(f"Dev user ready: {DEV_USER_ID}")
