"""Google OAuth provider — Architecture.md §8.2, Features.md "Google OAuth
login". A thin, testable boundary around Google's Authorization Code flow:
AuthService and the auth router depend on this class, never on raw httpx
calls to Google, so activating real OAuth later is a config change
(GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REDIRECT_URI), not a rewrite.

Fully implemented, but inert until those three env vars are set — see
`is_configured` and backend/README.md "Google OAuth status".
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import Settings

_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPE = "openid email profile"


class GoogleOAuthError(Exception):
    """Raised for any failure talking to Google (bad/expired code, network
    error, malformed response) — callers don't need to know which.
    """


@dataclass(frozen=True, slots=True)
class GoogleUserInfo:
    google_id: str
    email: str
    email_verified: bool
    full_name: str | None
    avatar_url: str | None


class GoogleOAuthProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        s = self._settings
        return bool(s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET and s.GOOGLE_REDIRECT_URI)

    def build_authorization_url(self, *, state: str) -> str:
        params = {
            "client_id": self._settings.GOOGLE_CLIENT_ID,
            "redirect_uri": self._settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": _SCOPE,
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{_AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

    async def exchange_code(self, *, code: str) -> GoogleUserInfo:
        """Authorization Code → tokens → userinfo, in one round trip.

        Never logs `code` or the access token it exchanges for — only the
        resulting profile fields (already non-secret) are returned.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                token_response = await client.post(
                    _TOKEN_ENDPOINT,
                    data={
                        "code": code,
                        "client_id": self._settings.GOOGLE_CLIENT_ID,
                        "client_secret": self._settings.GOOGLE_CLIENT_SECRET,
                        "redirect_uri": self._settings.GOOGLE_REDIRECT_URI,
                        "grant_type": "authorization_code",
                    },
                )
                token_response.raise_for_status()
                access_token = token_response.json()["access_token"]

                userinfo_response = await client.get(
                    _USERINFO_ENDPOINT,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                userinfo_response.raise_for_status()
                payload = userinfo_response.json()
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise GoogleOAuthError("failed to exchange authorization code with Google") from exc

        try:
            return GoogleUserInfo(
                google_id=payload["sub"],
                email=payload["email"],
                email_verified=bool(payload.get("email_verified", False)),
                full_name=payload.get("name"),
                avatar_url=payload.get("picture"),
            )
        except KeyError as exc:
            raise GoogleOAuthError("Google userinfo response missing required fields") from exc
