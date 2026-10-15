from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings

_PLACEHOLDER_JWT_SECRETS = frozenset(
    {
        "change-me-in-production",
        "your-secret-key-here",
    }
)


class Settings(BaseSettings):
    database_url: str = "sqlite:////data/boone_gifts.db"
    test_database_url: str = "sqlite:////data/boone_gifts_test.db"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = ["http://localhost:3000"]

    rate_limit_enabled: bool = True
    rate_limit_login: str = "10/minute"
    rate_limit_register: str = "5/minute"
    rate_limit_refresh: str = "30/minute"
    rate_limit_forgot_password: str = "5/minute"

    frontend_url: str = "https://boone-gifts.localhost"

    email_provider: str = "log"
    email_from: str = "Boone Gifts <noreply@boone-gifts.localhost>"
    email_reply_to: str = ""
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_username: str = ""
    email_smtp_password: str = ""
    email_smtp_use_tls: bool = True
    resend_api_key: str = ""

    linkpreview_api_key: str = ""

    sentry_dsn: str = ""
    sentry_release: str = ""
    # The deployed commit, injected by Coolify ("Include SOURCE_COMMIT in build"). Unprefixed
    # because Coolify names it; read through ``release``, never directly.
    source_commit: str = Field(default="", validation_alias="SOURCE_COMMIT")
    # One variable for every telemetry consumer: Sentry's ``environment`` and OTel's
    # ``deployment.environment``. APP_SENTRY_ENVIRONMENT is the pre-contract name, kept as a
    # fallback so an environment that still sets only that one is not relabelled.
    environment: str = Field(
        default="production",
        validation_alias=AliasChoices("APP_ENVIRONMENT", "APP_SENTRY_ENVIRONMENT"),
    )

    model_config = {"env_prefix": "APP_", "env_file": ".env"}

    @property
    def release(self) -> str | None:
        """The git SHA errors are tagged with: APP_SENTRY_RELEASE if set, else SOURCE_COMMIT.

        Coolify's literal ``unknown`` (no commit to give) is passed through, not dropped: OTel's
        ``service.version`` carries the same value, and the contract is that they agree.
        """
        for candidate in (self.sentry_release, self.source_commit):
            if value := candidate.strip():
                return value
        return None

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError(
                "APP_JWT_SECRET must be set to a non-empty value. "
                "Generate one with: openssl rand -hex 32"
            )
        if value in _PLACEHOLDER_JWT_SECRETS:
            raise ValueError(
                f"APP_JWT_SECRET is set to a placeholder value ({value!r}). "
                "Generate a real secret with: openssl rand -hex 32"
            )
        return value


settings = Settings()
