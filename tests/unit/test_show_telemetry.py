import pytest

from app.cli.show_telemetry import describe
from app.config import Settings


@pytest.fixture
def telemetry_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("APP_JWT_SECRET", "0123456789abcdef")
    for name in (
        "SOURCE_COMMIT",
        "APP_SENTRY_RELEASE",
        "APP_ENVIRONMENT",
        "APP_SENTRY_ENVIRONMENT",
        "APP_SENTRY_DSN",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_reports_the_resolved_pair(telemetry_env: pytest.MonkeyPatch) -> None:
    telemetry_env.setenv("SOURCE_COMMIT", "abc123")
    telemetry_env.setenv("APP_ENVIRONMENT", "production")
    telemetry_env.setenv("APP_SENTRY_DSN", "https://key@bugsink.example/1")
    assert (
        describe(Settings(_env_file=None))
        == "release=abc123 environment=production sentry=on"
    )


def test_reports_an_unset_release_and_disabled_sentry(
    telemetry_env: pytest.MonkeyPatch,
) -> None:
    assert (
        describe(Settings(_env_file=None))
        == "release=unset environment=production sentry=off"
    )
