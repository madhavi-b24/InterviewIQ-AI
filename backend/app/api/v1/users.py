"""Users API — API.md §1 (GET /users/me)."""

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.user import UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_my_profile(current_user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(current_user)
