"""Users API — API.md §1 (GET /users/me, PATCH /users/me)."""

from fastapi import APIRouter

from app.api.deps import AuthServiceDep, CurrentUser
from app.schemas.user import UserPublic, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_my_profile(current_user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.patch("/me")
async def update_my_profile(
    data: UserUpdateRequest, current_user: CurrentUser, auth_service: AuthServiceDep
) -> UserPublic:
    """Updates only the caller's own record — `current_user` is loaded
    from the bearer token by CurrentUser, never from a path/body id, so
    there is no id parameter for a caller to substitute another user's id
    into. Editable fields are limited by UserUpdateRequest's own shape,
    not by any check here (see its docstring for what's deliberately
    excluded).
    """
    user = await auth_service.update_profile(user=current_user, data=data)
    return UserPublic.model_validate(user)
