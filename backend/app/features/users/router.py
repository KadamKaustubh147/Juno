from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import CurrentUserId
from app.dependencies import get_db
from app.features.users import service
from app.features.users.schemas import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(user_id: CurrentUserId, db: Session = Depends(get_db)):
    return service.get_user(db, user_id)


@router.patch("/me", response_model=UserOut)
def update_me(body: UserUpdate, user_id: CurrentUserId, db: Session = Depends(get_db)):
    user = service.update_profile(db, user_id, body.full_name)
    # Commit before responding: get_db's own commit only runs after the response has gone out.
    db.commit()
    return user
