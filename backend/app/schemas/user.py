"""Public-facing user representations. Never includes password_hash —
this is the only shape a User model is allowed to leave the API layer as.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

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
