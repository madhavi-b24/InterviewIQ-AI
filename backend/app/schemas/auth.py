"""Request/response DTOs for the auth API (API.md §1).

Validation lives here, at the boundary — services trust these shapes and
never re-validate email format/password strength themselves.
"""

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.user import UserPublic


def _validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters long")
    if not any(char.isalpha() for char in password):
        raise ValueError("password must contain at least one letter")
    if not any(char.isdigit() for char in password):
        raise ValueError("password must contain at least one digit")
    return password


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)

    @field_validator("first_name", "last_name")
    @classmethod
    def names_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(TokenPair):
    """Returned by register, login, and the Google OAuth callback — the
    three flows that end with "here is a session for this user".
    """

    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class PasswordResetRequestRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return _validate_password_strength(value)
