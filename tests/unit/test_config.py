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


def test_rejects_env_example_placeholder_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


SHA = "3f2a9c1e0b7d4a6f8e5c2b1a0d9e8f7c6b5a4d3e"


@pytest.fixture
def telemetry_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A clean slate for the release/environment variables, whatever the host has set."""
    monkeypatch.setenv("APP_JWT_SECRET", "0123456789abcdef")
    for name in (
        "SOURCE_COMMIT",
        "APP_SENTRY_RELEASE",
        "APP_ENVIRONMENT",
        "APP_SENTRY_ENVIRONMENT",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_release_defaults_to_source_commit(telemetry_env: pytest.MonkeyPatch) -> None:
    telemetry_env.setenv("SOURCE_COMMIT", SHA)
    assert Settings(_env_file=None).release == SHA


def test_explicit_sentry_release_wins_over_source_commit(
    telemetry_env: pytest.MonkeyPatch,
) -> None:
    telemetry_env.setenv("SOURCE_COMMIT", SHA)
    telemetry_env.setenv("APP_SENTRY_RELEASE", "v1.2.3")
    assert Settings(_env_file=None).release == "v1.2.3"


@pytest.mark.parametrize("value", ["", "   "])
def test_release_is_unset_without_a_commit(
    telemetry_env: pytest.MonkeyPatch, value: str
) -> None:
    telemetry_env.setenv("SOURCE_COMMIT", value)
    telemetry_env.setenv("APP_SENTRY_RELEASE", value)
    assert Settings(_env_file=None).release is None


def test_release_passes_coolify_unknown_through(
    telemetry_env: pytest.MonkeyPatch,
) -> None:
    # Coolify's value when "Include SOURCE_COMMIT in build" is off. OTel's service.version
    # reports it verbatim, so Sentry must too.
    telemetry_env.setenv("SOURCE_COMMIT", "unknown")
    assert Settings(_env_file=None).release == "unknown"


def test_environment_reads_the_shared_variable(
    telemetry_env: pytest.MonkeyPatch,
) -> None:
    telemetry_env.setenv("APP_ENVIRONMENT", "staging")
    assert Settings(_env_file=None).environment == "staging"


def test_shared_environment_wins_over_legacy_sentry_variable(
    telemetry_env: pytest.MonkeyPatch,
) -> None:
    telemetry_env.setenv("APP_ENVIRONMENT", "staging")
    telemetry_env.setenv("APP_SENTRY_ENVIRONMENT", "production")
    assert Settings(_env_file=None).environment == "staging"


def test_environment_falls_back_to_legacy_sentry_variable(
    telemetry_env: pytest.MonkeyPatch,
) -> None:
    telemetry_env.setenv("APP_SENTRY_ENVIRONMENT", "development")
    assert Settings(_env_file=None).environment == "development"


def test_environment_defaults_to_production(telemetry_env: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).environment == "production"
