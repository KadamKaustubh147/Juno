"""Password hashing (argon2id, via argon2-cffi's defaults)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """False for a wrong password *and* for a hash that isn't one (e.g. the seeded dev user's '!')."""
    try:
        return _hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False
