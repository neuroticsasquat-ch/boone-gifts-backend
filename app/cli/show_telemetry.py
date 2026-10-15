"""Print the release and environment errors are reported under, as the app resolves them."""

from app.config import Settings, settings


def describe(config: Settings) -> str:
    sentry = "on" if config.sentry_dsn else "off"
    return f"release={config.release or 'unset'} environment={config.environment} sentry={sentry}"


def main() -> None:
    print(describe(settings))


if __name__ == "__main__":
    main()
