"""Auth domain repositories — Database.md §2."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models.user import PasswordResetToken, RefreshToken, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_google_id(self, google_id: str) -> User | None:
        result = await self._session.execute(select(User).where(User.google_id == google_id))
        return result.scalar_one_or_none()


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_token_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        """Same lookup as get_by_token_hash, but with SELECT ... FOR UPDATE.

        Without this, two concurrent /auth/refresh calls presenting the
        same (not-yet-revoked) token both read revoked_at IS NULL under
        READ COMMITTED, and both proceed to rotate — forking two valid
        sessions from what should be a single-use token. The row lock
        makes the second caller block until the first commits its
        rotation, then it re-reads the now-revoked row and correctly
        rejects the replay.
        """
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)
        await self._session.flush()


class PasswordResetTokenRepository(BaseRepository[PasswordResetToken]):
    model = PasswordResetToken

    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        result = await self._session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_token_hash_for_update(self, token_hash: str) -> PasswordResetToken | None:
        """Same lookup as get_by_token_hash, but with SELECT ... FOR UPDATE
        — see RefreshTokenRepository.get_by_token_hash_for_update for why:
        the same race applies to two concurrent confirm_password_reset
        calls racing on used_at IS NULL for the same token.
        """
        result = await self._session.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token: PasswordResetToken) -> None:
        token.used_at = datetime.now(UTC)
        await self._session.flush()
