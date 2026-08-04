"""JWT + password hashing primitives.

This is infrastructure, not the auth feature itself: it knows how to mint
and verify tokens and hash passwords. It does not know about registration,
login rules, or OAuth flows — that use-case logic belongs to Module 2's
AuthService.
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(plain_password, password_hash)


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def _create_token(subject: uuid.UUID, token_type: TokenType, expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    return _create_token(
        user_id, TokenType.ACCESS, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    return _create_token(
        user_id, TokenType.REFRESH, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


class InvalidTokenError(Exception):
    """Raised for any decode failure: bad signature, expired, malformed, wrong type."""


def decode_token(token: str, expected_type: TokenType) -> uuid.UUID:
    """Decode and validate a token, returning the user id encoded in `sub`.

    Raises InvalidTokenError for any failure — callers don't need to know
    whether it was expiry, signature, or shape that failed.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"expected token type {expected_type.value!r}")

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("token missing a valid subject") from exc
