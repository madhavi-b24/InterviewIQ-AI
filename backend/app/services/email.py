"""Email delivery abstraction — Features.md "Password reset flow".

AuthService depends on this Protocol, never on a concrete provider —
swapping the console mock for a real provider (SES, SendGrid, Postmark,
...) later is a new class + a config flip (EMAIL_PROVIDER), not a refactor.

No production provider is implemented yet: this milestone is backend-auth
scope, not email infra. `ConsoleEmailProvider` is the only implementation,
and it never sends real email — see its docstring for why it also never
logs the reset token.
"""

from typing import Protocol

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailProvider(Protocol):
    async def send_password_reset_email(self, *, to: str, reset_token: str) -> None: ...


class ConsoleEmailProvider:
    """Development-only mock. Records that a reset email *would* have been
    sent, without ever sending real email.

    Deliberately does NOT print or log `reset_token` anywhere — stdout in a
    running container is itself a log stream (`docker compose logs`), so
    printing the token would violate the "never log reset tokens" security
    requirement just as much as structlog would. Tests that need the raw
    token use a dependency override with a capturing test double instead
    (see tests/conftest.py's FakeEmailProvider) — that is the intended way
    to observe it, not this class.

    Refuses to run in production so a missing real provider fails loudly
    at startup instead of silently discarding every reset email.
    """

    def __init__(self, settings: Settings) -> None:
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(
                "ConsoleEmailProvider must not be used in production; "
                "configure a real EMAIL_PROVIDER before deploying"
            )

    async def send_password_reset_email(self, *, to: str, reset_token: str) -> None:
        logger.info("email.password_reset.sent_console_mock", to=to)
