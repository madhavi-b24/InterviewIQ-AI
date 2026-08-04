"""JWT + password hashing primitives.

This is infrastructure, not the auth feature itself: it knows how to mint
and verify tokens and hash passwords. It does not know about registration,
login rules, or OAuth flows — that use-case logic belongs to Module 2's
AuthService.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# Argon2id (passlib's default argon2 "type") — winner of the Password
# Hashing Competition, memory-hard by design (resists GPU/ASIC cracking
# far better than bcrypt). "bcrypt" stays listed only so any pre-existing
# bcrypt hash still verifies; passlib's `deprecated="auto"` transparently
# reports such a hash as needing a rehash, but nothing here creates new
# bcrypt hashes.
_pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

# A real hash of a fixed, never-used password. verify_password() runs
# against this when a user/account lookup fails, so a login attempt for a
# nonexistent email takes the same time as one for a real email with a
# wrong password — timing is not a viable user-enumeration oracle.
_DUMMY_PASSWORD_HASH = _pwd_context.hash("dummy-password-for-constant-time-comparison")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str | None) -> bool:
    return _pwd_context.verify(plain_password, password_hash or _DUMMY_PASSWORD_HASH)


def hash_token(raw_token: str) -> str:
    """SHA-256 of an opaque, high-entropy token (refresh/reset tokens).

    Unlike passwords, these tokens are generated with 256 bits of entropy
    (see generate_opaque_token) — a fast deterministic hash is appropriate
    here because brute-forcing the token itself, not the hash, is the
    attacker's only path; a slow password-hashing KDF would just add
    latency on every refresh/reset without a security benefit.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_opaque_token() -> str:
    """Cryptographically secure, URL-safe token for refresh/reset flows."""
    return secrets.token_urlsafe(32)


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
        # jose encodes "iat"/"exp" datetimes as whole-second Unix
        # timestamps, so two tokens for the same user/type/expiry minted
        # within the same second would otherwise be byte-identical —
        # which breaks refresh_tokens.token_hash's uniqueness constraint
        # (e.g. register() then login() in the same second). A random
        # jti guarantees every token is unique regardless of timing.
        "jti": str(uuid.uuid4()),
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
