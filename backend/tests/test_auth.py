"""Auth module tests — registration, login, JWT, refresh rotation,
authorization, logout, password reset, and targeted security properties.
"""

import asyncio
from datetime import timedelta
from unittest import mock

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.deps import get_google_oauth_provider, require_role
from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import TokenType, _create_token, decode_token
from app.db.session import get_session_factory
from app.main import app
from app.models.enums import UserRole
from app.models.user import PasswordResetToken, RefreshToken, User
from app.services.auth_service import AuthService
from app.services.oauth import GoogleUserInfo

VALID_PASSWORD = "correct-horse-42"


async def _register(
    client: AsyncClient, *, email: str = "ada@example.com", password: str = VALID_PASSWORD
):
    return await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Ada",
            "last_name": "Lovelace",
        },
    )


# --- Registration ------------------------------------------------------


async def test_register_success(client: AsyncClient) -> None:
    response = await _register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["role"] == "candidate"
    assert body["user"]["is_active"] is True
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_register_normalizes_email_case_and_whitespace(client: AsyncClient) -> None:
    response = await _register(client, email="  Ada@Example.com  ")
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "ada@example.com"


async def test_register_duplicate_email(client: AsyncClient) -> None:
    first = await _register(client)
    assert first.status_code == 201

    second = await _register(client)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"


async def test_register_invalid_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": VALID_PASSWORD,
            "first_name": "Ada",
            "last_name": "Lovelace",
        },
    )
    assert response.status_code == 422


async def test_register_weak_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ada@example.com",
            "password": "weak",
            "first_name": "Ada",
            "last_name": "Lovelace",
        },
    )
    assert response.status_code == 422


async def test_register_weak_password_does_not_echo_password_in_response(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ada@example.com",
            "password": "super-secret-weak-attempt",
            "first_name": "Ada",
            "last_name": "Lovelace",
        },
    )
    assert response.status_code == 422
    assert "super-secret-weak-attempt" not in response.text


# --- Login ---------------------------------------------------------------


async def test_login_success(client: AsyncClient) -> None:
    await _register(client)

    response = await client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_wrong_password(client: AsyncClient) -> None:
    await _register(client)

    response = await client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": "wrong-password-1"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "invalid email or password"


async def test_login_nonexistent_user(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "whatever-123"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "invalid email or password"


# --- JWT / current-user endpoint -----------------------------------------


async def test_me_with_valid_access_token(client: AsyncClient) -> None:
    tokens = (await _register(client)).json()

    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


async def test_me_without_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_me_with_invalid_token(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer garbage.not.a.jwt"}
    )
    assert response.status_code == 401


async def test_me_with_expired_access_token(client: AsyncClient) -> None:
    tokens = (await _register(client)).json()
    user_id = decode_token(tokens["access_token"], TokenType.ACCESS)
    expired = _create_token(user_id, TokenType.ACCESS, timedelta(minutes=-1))

    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


async def test_refresh_token_cannot_be_used_as_access_token(client: AsyncClient) -> None:
    tokens = (await _register(client)).json()

    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert response.status_code == 401


# --- Refresh ---------------------------------------------------------------


async def test_refresh_success(client: AsyncClient) -> None:
    tokens = (await _register(client)).json()

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


async def test_refresh_expired_token(client: AsyncClient) -> None:
    tokens = (await _register(client)).json()
    user_id = decode_token(tokens["refresh_token"], TokenType.REFRESH)
    expired = _create_token(user_id, TokenType.REFRESH, timedelta(days=-1))

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": expired})
    assert response.status_code == 401


async def test_refresh_revoked_token_cannot_be_reused(client: AsyncClient) -> None:
    tokens = (await _register(client)).json()

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first.status_code == 200

    reuse = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reuse.status_code == 401


async def test_refresh_rotation_persists_hashed_not_raw(client: AsyncClient) -> None:
    tokens = (await _register(client)).json()

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(RefreshToken))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].token_hash != tokens["refresh_token"]
        assert rows[0].revoked_at is None


async def test_refresh_rolls_back_completely_if_new_token_issuance_fails(
    client: AsyncClient,
) -> None:
    """If minting the replacement pair fails mid-rotation, the old token
    must not be left revoked without a replacement — revoke + reissue must
    commit atomically or not at all (AuthService.refresh's single trailing
    commit() relies on Session.close() rolling back anything flushed-but-
    uncommitted when an exception propagates before that commit).
    """
    tokens = (await _register(client)).json()

    session_factory = get_session_factory()
    async with session_factory() as session:
        auth_service = AuthService(session, get_settings())
        with (
            mock.patch.object(
                AuthService, "_issue_token_pair", side_effect=RuntimeError("simulated failure")
            ),
            pytest.raises(RuntimeError),
        ):
            await auth_service.refresh(tokens["refresh_token"])
    # session closed above without ever calling commit() -> SQLAlchemy
    # rolls back the flushed-but-uncommitted revoke.

    async with session_factory() as session:
        result = await session.execute(select(RefreshToken))
        row = result.scalar_one()
        assert row.revoked_at is None

    # The original token must still work normally afterward — it was
    # never actually consumed.
    retry = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert retry.status_code == 200


async def test_concurrent_refresh_with_same_token_only_one_succeeds(client: AsyncClient) -> None:
    """Two simultaneous /auth/refresh calls with the identical (valid,
    not-yet-revoked) refresh token must not both succeed — that would fork
    two live sessions from a token that's supposed to be single-use. The
    SELECT ... FOR UPDATE lock in get_by_token_hash_for_update serializes
    them: the second blocks until the first commits, then sees the token
    already revoked.
    """
    tokens = (await _register(client)).json()
    session_factory = get_session_factory()

    async def _refresh_in_own_session() -> int:
        async with session_factory() as session:
            auth_service = AuthService(session, get_settings())
            try:
                await auth_service.refresh(tokens["refresh_token"])
                return 200
            except UnauthorizedError:
                return 401

    results = await asyncio.gather(
        _refresh_in_own_session(), _refresh_in_own_session(), _refresh_in_own_session()
    )

    assert results.count(200) == 1
    assert results.count(401) == 2


# --- Authorization (require_role) -----------------------------------------


def test_require_role_allows_matching_role() -> None:
    user = User(email="a@b.com", full_name="A B", auth_provider="local", role=UserRole.CANDIDATE)
    checked = require_role(UserRole.CANDIDATE, UserRole.ADMIN)(user)
    assert checked is user


def test_require_role_forbids_non_matching_role() -> None:
    user = User(email="a@b.com", full_name="A B", auth_provider="local", role=UserRole.CANDIDATE)
    with pytest.raises(ForbiddenError) as exc_info:
        require_role(UserRole.ADMIN)(user)
    assert exc_info.value.status_code == 403


# --- Logout ------------------------------------------------------------


async def test_logout_success(client: AsyncClient) -> None:
    tokens = (await _register(client)).json()

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 204


async def test_logout_revokes_refresh_session(client: AsyncClient) -> None:
    tokens = (await _register(client)).json()

    await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401


async def test_logout_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout", json={"refresh_token": "whatever"})
    assert response.status_code == 401


# --- Password reset ------------------------------------------------------


async def test_password_reset_request_unknown_email_is_silent(
    client: AsyncClient, fake_email_provider
) -> None:
    response = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 202
    assert fake_email_provider.sent == []


async def test_password_reset_full_flow(client: AsyncClient, fake_email_provider) -> None:
    await _register(client)

    request_response = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": "ada@example.com"}
    )
    assert request_response.status_code == 202
    assert len(fake_email_provider.sent) == 1
    to, reset_token = fake_email_provider.sent[0]
    assert to == "ada@example.com"

    confirm_response = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "brand-new-pass-1"},
    )
    assert confirm_response.status_code == 204

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": VALID_PASSWORD}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "brand-new-pass-1"},
    )
    assert new_login.status_code == 200


async def test_password_reset_token_is_single_use(client: AsyncClient, fake_email_provider) -> None:
    await _register(client)
    await client.post("/api/v1/auth/password-reset/request", json={"email": "ada@example.com"})
    _, reset_token = fake_email_provider.sent[0]

    first = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "brand-new-pass-1"},
    )
    assert first.status_code == 204

    second = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "another-pass-2"},
    )
    assert second.status_code == 401


async def test_concurrent_password_reset_confirm_with_same_token_only_one_succeeds(
    client: AsyncClient, fake_email_provider
) -> None:
    """Two simultaneous confirm calls with the identical (valid, unused)
    reset token must not both succeed — see get_by_token_hash_for_update.
    Without the row lock, both would read used_at IS NULL under READ
    COMMITTED and both proceed.
    """
    await _register(client)
    await client.post("/api/v1/auth/password-reset/request", json={"email": "ada@example.com"})
    _, reset_token = fake_email_provider.sent[0]

    session_factory = get_session_factory()

    async def _confirm_in_own_session(new_password: str) -> int:
        async with session_factory() as session:
            auth_service = AuthService(session, get_settings())
            try:
                await auth_service.confirm_password_reset(
                    token=reset_token, new_password=new_password
                )
                return 204
            except UnauthorizedError:
                return 401

    results = await asyncio.gather(
        _confirm_in_own_session("attempt-pass-1"),
        _confirm_in_own_session("attempt-pass-2"),
        _confirm_in_own_session("attempt-pass-3"),
    )

    assert results.count(204) == 1
    assert results.count(401) == 2

    async with session_factory() as session:
        result = await session.execute(select(PasswordResetToken))
        row = result.scalar_one()
        assert row.used_at is not None


async def test_password_reset_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "not-a-real-token", "new_password": "brand-new-pass-1"},
    )
    assert response.status_code == 401


async def test_password_reset_revokes_existing_refresh_sessions(
    client: AsyncClient, fake_email_provider
) -> None:
    tokens = (await _register(client)).json()

    await client.post("/api/v1/auth/password-reset/request", json={"email": "ada@example.com"})
    _, reset_token = fake_email_provider.sent[0]
    await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "brand-new-pass-1"},
    )

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401


# --- Google OAuth boundary -------------------------------------------------


async def test_google_login_returns_503_when_not_configured(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/google/login")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


class _FakeGoogleOAuthProvider:
    """Stands in for a configured GoogleOAuthProvider without real Google
    credentials — same interface, exchange_code() returns a canned profile
    instead of calling Google.
    """

    is_configured = True

    def build_authorization_url(self, *, state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}&mock=1"

    async def exchange_code(self, *, code: str) -> GoogleUserInfo:
        return GoogleUserInfo(
            google_id="fake-google-id",
            email="oauth-user@example.com",
            email_verified=True,
            full_name="OAuth User",
            avatar_url=None,
        )


async def test_google_oauth_state_is_single_use_and_expires(client: AsyncClient) -> None:
    from urllib.parse import parse_qs, urlparse

    from redis.asyncio import Redis

    from app.cache.redis_client import get_redis_pool

    app.dependency_overrides[get_google_oauth_provider] = lambda: _FakeGoogleOAuthProvider()
    try:
        login_response = await client.get("/api/v1/auth/google/login")
        assert login_response.status_code == 307
        state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

        redis = Redis(connection_pool=get_redis_pool())
        try:
            ttl = await redis.ttl(f"oauth_state:{state}")
            assert 0 < ttl <= 300
        finally:
            await redis.aclose()

        first = await client.get(
            "/api/v1/auth/google/callback", params={"code": "fake-code", "state": state}
        )
        assert first.status_code == 200
        assert first.json()["user"]["email"] == "oauth-user@example.com"

        # Same state again: already consumed by the first callback.
        second = await client.get(
            "/api/v1/auth/google/callback", params={"code": "fake-code", "state": state}
        )
        assert second.status_code == 401
    finally:
        app.dependency_overrides.pop(get_google_oauth_provider, None)


async def test_google_oauth_refuses_to_link_unverified_email(client: AsyncClient) -> None:
    """Google asserting email_verified=False must not be enough to attach
    a Google identity to an existing local account by email match alone.
    """
    await _register(client)

    session_factory = get_session_factory()
    async with session_factory() as session:
        auth_service = AuthService(session, get_settings())
        google_user = GoogleUserInfo(
            google_id="google-unverified-123",
            email="ada@example.com",
            email_verified=False,
            full_name="Ada L",
            avatar_url=None,
        )
        with pytest.raises(UnauthorizedError):
            await auth_service.login_or_register_google_user(google_user)


async def test_google_oauth_links_verified_email_to_existing_account(client: AsyncClient) -> None:
    await _register(client)

    session_factory = get_session_factory()
    async with session_factory() as session:
        auth_service = AuthService(session, get_settings())
        google_user = GoogleUserInfo(
            google_id="google-verified-456",
            email="ada@example.com",
            email_verified=True,
            full_name="Ada L",
            avatar_url=None,
        )
        user, tokens = await auth_service.login_or_register_google_user(google_user)
        assert user.google_id == "google-verified-456"
        assert user.is_verified is True
        assert tokens.access_token


# --- Security properties --------------------------------------------------


async def test_password_hash_uses_argon2(client: AsyncClient) -> None:
    await _register(client)

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.email == "ada@example.com"))
        user = result.scalar_one()
        assert user.password_hash.startswith("$argon2")
