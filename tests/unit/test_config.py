import pytest
from pydantic import ValidationError

from app.config import Settings


def _settings(monkeypatch: pytest.MonkeyPatch, value: str) -> Settings:
    monkeypatch.setenv("APP_JWT_SECRET", value)
    return Settings(_env_file=None)


def test_rejects_placeholder_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_JWT_SECRET", "change-me-in-production")
    with pytest.raises(ValidationError, match="APP_JWT_SECRET"):
        Settings(_env_file=None)


def test_rejects_env_example_placeholder_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_JWT_SECRET", "your-secret-key-here")
    with pytest.raises(ValidationError, match="APP_JWT_SECRET"):
        Settings(_env_file=None)


def test_rejects_empty_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_JWT_SECRET", "")
    with pytest.raises(ValidationError, match="APP_JWT_SECRET"):
        Settings(_env_file=None)


def test_rejects_whitespace_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_JWT_SECRET", "   ")
    with pytest.raises(ValidationError, match="APP_JWT_SECRET"):
        Settings(_env_file=None)


def test_rejects_missing_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_accepts_real_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    real_secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    settings = _settings(monkeypatch, real_secret)
    assert settings.jwt_secret == real_secret
