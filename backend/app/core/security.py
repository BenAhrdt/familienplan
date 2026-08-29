import hashlib
import secrets
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, digest: str) -> bool:
    try:
        return password_hasher.verify(digest, password)
    except VerifyMismatchError:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(48)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)

