"""Settings validation — CORS misconfiguration guard (consistency review
item: CORS_ORIGINS must never be able to pair a wildcard origin with
allow_credentials=True, which app.main.create_app() always sets).
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_rejects_wildcard() -> None:
    with pytest.raises(ValidationError):
        Settings(CORS_ORIGINS=["*"])


def test_cors_origins_rejects_wildcard_mixed_with_real_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(CORS_ORIGINS=["http://localhost:5173", "*"])


def test_cors_origins_accepts_explicit_origins() -> None:
    settings = Settings(CORS_ORIGINS=["http://localhost:5173", "https://app.example.com"])
    assert settings.CORS_ORIGINS == ["http://localhost:5173", "https://app.example.com"]
