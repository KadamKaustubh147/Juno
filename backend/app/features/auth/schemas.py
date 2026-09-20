from pydantic import BaseModel, EmailStr, Field

from app.features.users.schemas import UserOut


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    # Plain str, not EmailStr: login only looks the address up, and format validation would
    # lock out any stored address the validator rejects (e.g. the seeded dev@juno.local).
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
