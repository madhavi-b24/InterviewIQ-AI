"""AuthService — the use-case layer for registration, login, refresh
rotation, logout, and password reset (Architecture.md §4). Routers call
exactly these methods; no SQL or token logic lives in app/api/v1/auth.py.

Transaction ownership: each public method commits exactly once, at the
end, after every repository mutation it needs has been flushed. A
duplicate-email race is the one place two transactions can legitimately
conflict (both requests pass the pre-check, then IntegrityError fires
on commit) — see register().
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.enums import AuthProvider, UserRole
from app.models.user import PasswordResetToken, RefreshToken, User
from app.repositories.user import (
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.schemas.auth import RegisterRequest, TokenPair
from app.services.email import EmailProvider
from app.services.oauth import GoogleUserInfo


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)
        self._refresh_tokens = RefreshTokenRepository(session)
        self._reset_tokens = PasswordResetTokenRepository(session)

    # --- Registration ----------------------------------------------------

    async def register(self, data: RegisterRequest) -> tuple[User, TokenPair]:
        email = data.email.strip().lower()
        if await self._users.get_by_email(email) is not None:
            raise ConflictError("an account with this email already exists")

        user = User(
            email=email,
            password_hash=hash_password(data.password),
            full_name=f"{data.first_name} {data.last_name}".strip(),
            auth_provider=AuthProvider.LOCAL,
            role=UserRole.CANDIDATE,
        )
        await self._users.add(user)
        token_pair = await self._issue_token_pair(user)

        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("an account with this email already exists") from exc

        return user, token_pair

    # --- Login -------------------------------------------------------------

    async def login(self, *, email: str, password: str) -> tuple[User, TokenPair]:
        user = await self._users.get_by_email(email.strip().lower())
        password_ok = verify_password(password, user.password_hash if user else None)

        if user is None or not user.is_active or not password_ok:
            raise UnauthorizedError("invalid email or password")

        token_pair = await self._issue_token_pair(user)
        await self._session.commit()
        return user, token_pair

    # --- Token refresh / rotation -------------------------------------------

    async def refresh(self, raw_refresh_token: str) -> tuple[User, TokenPair]:
        try:
            user_id = decode_token(raw_refresh_token, TokenType.REFRESH)
        except InvalidTokenError as exc:
            raise UnauthorizedError("invalid or expired refresh token") from exc

        # FOR UPDATE: locks this row for the rest of the transaction, so a
        # concurrent replay of the same token blocks here instead of both
        # requests reading "not yet revoked" and both rotating — see
        # RefreshTokenRepository.get_by_token_hash_for_update.
        stored = await self._refresh_tokens.get_by_token_hash_for_update(
            hash_token(raw_refresh_token)
        )
        if not self._is_usable(stored, expected_user_id=user_id):
            raise UnauthorizedError("invalid or expired refresh token")

        user = await self._session.get(User, user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("invalid or expired refresh token")

        # Rotation: this refresh token is single-use. Revoking it here means
        # a replayed copy of the same token is rejected by _is_usable above
        # on its next use, even though its JWT signature/expiry still checks
        # out — the DB row, not the JWT alone, is the source of truth for
        # "is this session still alive".
        await self._refresh_tokens.revoke(stored)
        token_pair = await self._issue_token_pair(user)
        await self._session.commit()
        return user, token_pair

    @staticmethod
    def _is_usable(token: RefreshToken | None, *, expected_user_id: uuid.UUID) -> bool:
        if token is None or token.revoked_at is not None or token.user_id != expected_user_id:
            return False
        return token.expires_at >= datetime.now(UTC)

    # --- Logout --------------------------------------------------------------

    async def logout(self, *, user: User, raw_refresh_token: str) -> None:
        """Revokes the given refresh session if it belongs to `user` and
        isn't already revoked. Idempotent and silent otherwise — logout
        never leaks whether a token existed, belonged to someone else, or
        was already used; the client always sees a successful logout.
        """
        stored = await self._refresh_tokens.get_by_token_hash(hash_token(raw_refresh_token))
        if stored is not None and stored.user_id == user.id and stored.revoked_at is None:
            await self._refresh_tokens.revoke(stored)
            await self._session.commit()

    # --- Google OAuth ----------------------------------------------------

    async def login_or_register_google_user(
        self, google_user: GoogleUserInfo
    ) -> tuple[User, TokenPair]:
        user = await self._users.get_by_google_id(google_user.google_id)
        if user is None:
            email = google_user.email.strip().lower()
            user = await self._users.get_by_email(email)
            if user is None:
                user = User(
                    email=email,
                    password_hash=None,
                    full_name=google_user.full_name or email,
                    avatar_url=google_user.avatar_url,
                    auth_provider=AuthProvider.GOOGLE,
                    google_id=google_user.google_id,
                    role=UserRole.CANDIDATE,
                    is_verified=google_user.email_verified,
                )
                await self._users.add(user)
            elif google_user.email_verified:
                # Existing local account, same *Google-verified* email —
                # link Google as an additional sign-in method instead of
                # creating a duplicate account. auth_provider/password_hash
                # stay as-is so the password login path keeps working too.
                user.google_id = google_user.google_id
                user.is_verified = True
            else:
                # Google itself hasn't verified this email is controlled by
                # the person signing in — auto-linking it to an existing
                # account on email match alone would let anyone with an
                # unverified Google Workspace address claim someone else's
                # account. Refuse rather than silently linking.
                raise UnauthorizedError(
                    "Google account email is not verified; cannot link to an existing account"
                )

        if not user.is_active:
            raise UnauthorizedError("account is inactive")

        token_pair = await self._issue_token_pair(user)
        await self._session.commit()
        return user, token_pair

    # --- Password reset ----------------------------------------------------

    async def request_password_reset(self, *, email: str, email_provider: EmailProvider) -> None:
        """Always returns None with no observable difference for an
        unknown vs. known email — the only way to distinguish them must
        never be this endpoint's response.
        """
        user = await self._users.get_by_email(email.strip().lower())
        if user is None or not user.is_active:
            return

        raw_token = generate_opaque_token()
        reset_row = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC)
            + timedelta(minutes=self._settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
        await self._reset_tokens.add(reset_row)
        await self._session.commit()

        await email_provider.send_password_reset_email(to=user.email, reset_token=raw_token)

    async def confirm_password_reset(self, *, token: str, new_password: str) -> None:
        # FOR UPDATE: see get_by_token_hash_for_update — without this lock,
        # two concurrent confirms of the same token can both read
        # used_at IS NULL and both succeed, defeating single-use.
        stored = await self._reset_tokens.get_by_token_hash_for_update(hash_token(token))
        if not self._reset_token_usable(stored):
            raise UnauthorizedError("invalid or expired reset token")

        user = await self._session.get(User, stored.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("invalid or expired reset token")

        user.password_hash = hash_password(new_password)
        await self._reset_tokens.mark_used(stored)

        # A password reset is a strong signal the old password may have
        # been compromised — invalidate every existing session rather than
        # leaving them valid until their natural expiry.
        await self._revoke_all_refresh_tokens(user.id)

        await self._session.commit()

    @staticmethod
    def _reset_token_usable(token: PasswordResetToken | None) -> bool:
        if token is None or token.used_at is not None:
            return False
        return token.expires_at >= datetime.now(UTC)

    async def _revoke_all_refresh_tokens(self, user_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        now = datetime.now(UTC)
        for token in result.scalars():
            token.revoked_at = now

    # --- Shared -------------------------------------------------------------

    async def _issue_token_pair(self, user: User) -> TokenPair:
        access_token = create_access_token(user.id)
        raw_refresh_token = create_refresh_token(user.id)

        refresh_row = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=self._settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        await self._refresh_tokens.add(refresh_row)

        return TokenPair(access_token=access_token, refresh_token=raw_refresh_token)
