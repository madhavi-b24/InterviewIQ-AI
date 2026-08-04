"""Auth API — API.md §1. Routers only parse/validate HTTP concerns and
call AuthService; no SQL, password, or token logic here.
"""

import secrets

from fastapi import APIRouter, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import (
    AuthServiceDep,
    CurrentUser,
    EmailProviderDep,
    GoogleOAuthProviderDep,
    RedisClient,
)
from app.core.exceptions import ServiceUnavailableError, UnauthorizedError
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.user import UserPublic
from app.services.oauth import GoogleOAuthError

router = APIRouter(prefix="/auth", tags=["auth"])

# CSRF nonce for the OAuth redirect round trip — short-lived, single-use,
# stored in Redis rather than a cookie/session store we don't have yet.
_OAUTH_STATE_KEY_PREFIX = "oauth_state:"
_OAUTH_STATE_TTL_SECONDS = 300


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, auth_service: AuthServiceDep) -> AuthResponse:
    user, tokens = await auth_service.register(data)
    return AuthResponse(user=UserPublic.model_validate(user), **tokens.model_dump())


@router.post("/login")
async def login(data: LoginRequest, auth_service: AuthServiceDep) -> AuthResponse:
    user, tokens = await auth_service.login(email=data.email, password=data.password)
    return AuthResponse(user=UserPublic.model_validate(user), **tokens.model_dump())


@router.post("/refresh")
async def refresh_tokens(data: RefreshRequest, auth_service: AuthServiceDep) -> TokenPair:
    _user, tokens = await auth_service.refresh(data.refresh_token)
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: LogoutRequest, current_user: CurrentUser, auth_service: AuthServiceDep
) -> Response:
    """Revokes the refresh session named by `refresh_token` (see
    AuthService.logout for exact semantics). The access token handed to
    this same request is NOT invalidated — it remains valid, stateless,
    until it naturally expires (ACCESS_TOKEN_EXPIRE_MINUTES). Clients must
    discard both tokens locally on logout; the server-side guarantee this
    endpoint provides is that the refresh session can no longer mint new
    access tokens.
    """
    await auth_service.logout(user=current_user, raw_refresh_token=data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/google/login")
async def google_login(
    oauth_provider: GoogleOAuthProviderDep, redis: RedisClient
) -> RedirectResponse:
    if not oauth_provider.is_configured:
        raise ServiceUnavailableError(
            "Google OAuth is not configured on this server "
            "(GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REDIRECT_URI unset)"
        )
    state = secrets.token_urlsafe(24)
    await redis.set(f"{_OAUTH_STATE_KEY_PREFIX}{state}", "1", ex=_OAUTH_STATE_TTL_SECONDS)
    return RedirectResponse(oauth_provider.build_authorization_url(state=state))


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    oauth_provider: GoogleOAuthProviderDep,
    auth_service: AuthServiceDep,
    redis: RedisClient,
) -> AuthResponse:
    """Returns tokens directly as JSON rather than redirecting to a
    frontend URL — there is no frontend route to redirect to yet (this
    milestone is backend-only). A future frontend module will likely want
    this to redirect to e.g. `{FRONTEND_URL}/oauth/callback#access_token=...`
    instead; tracked as a TODO, not implemented here since inventing that
    contract without a frontend to consume it would be premature.
    """
    if not oauth_provider.is_configured:
        raise ServiceUnavailableError(
            "Google OAuth is not configured on this server "
            "(GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REDIRECT_URI unset)"
        )

    if not await redis.getdel(f"{_OAUTH_STATE_KEY_PREFIX}{state}"):
        raise UnauthorizedError("invalid or expired OAuth state")

    try:
        google_user = await oauth_provider.exchange_code(code=code)
    except GoogleOAuthError as exc:
        raise UnauthorizedError("failed to authenticate with Google") from exc

    user, tokens = await auth_service.login_or_register_google_user(google_user)
    return AuthResponse(user=UserPublic.model_validate(user), **tokens.model_dump())


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    data: PasswordResetRequestRequest,
    auth_service: AuthServiceDep,
    email_provider: EmailProviderDep,
) -> dict:
    await auth_service.request_password_reset(email=data.email, email_provider=email_provider)
    return {"message": "if an account exists for this email, a reset link has been sent"}


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    data: PasswordResetConfirmRequest, auth_service: AuthServiceDep
) -> Response:
    await auth_service.confirm_password_reset(token=data.token, new_password=data.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
