from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth.jwt import create_access_token
from app.dependencies import get_db
from app.features.auth import service
from app.features.auth.schemas import AuthResponse, LoginRequest, RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    user = service.register(db, body)
    # Commit before responding: get_db's own commit only runs after the response has gone out,
    # and the token is usable the instant the client gets it.
    db.commit()
    return AuthResponse(access_token=create_access_token(user.id), user=user)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = service.login(db, body)
    return AuthResponse(access_token=create_access_token(user.id), user=user)
