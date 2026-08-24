"""Public-facing user representations. Never includes password_hash —
this is the only shape a User model is allowed to leave the API layer as.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import UserRole


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    avatar_url: str | None
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime


class UserUpdateRequest(BaseModel):
    """PATCH /users/me (API.md §1: "Update profile (name, avatar)").
    Deliberately limited to these two fields — the only profile attributes
    the User model treats as candidate-owned, freely-editable text
    (Database.md §2). role/id/is_active/is_verified/auth_provider/
    google_id/email are absent on purpose — none of them are editable via
    this endpoint (email changes and verification-status changes each have
    their own, separate, more sensitive flow elsewhere).

    Partial-update semantics, deliberately simple: a field that's `None`
    — whether omitted or sent explicitly as `null` — leaves that column
    untouched; only a non-blank string value updates it. This endpoint
    does not support clearing avatar_url back to null (there's no
    upload/removal flow yet to pair that with) or clearing full_name
    (every account needs a non-blank display name) — both are reasonable
    limitations for this endpoint's scope, not oversights.
    """

    full_name: str | None = None
    avatar_url: str | None = None

    @field_validator("full_name", "avatar_url")
    @classmethod
    def not_blank_if_provided(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value
