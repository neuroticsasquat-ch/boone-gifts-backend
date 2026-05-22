from pydantic import field_validator
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

    model_config = {"env_prefix": "APP_", "env_file": ".env"}

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
