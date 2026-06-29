import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.auth import router as auth
from app.users import router as users
from app.invites import router as invites
from app.lists import router as lists
from app.gifts import router as gifts
from app.shares import router as shares
from app.connections import router as connections
from app.collections import router as collections_
from app.meta import router as meta
from app.families import router as families
from app.family_invites import router as family_invites


def create_app() -> FastAPI:
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            release=settings.sentry_release or None,
            send_default_pii=False,
            traces_sample_rate=0.1,
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
        )

    application = FastAPI(title="Boone Gifts API")

    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth.router)
    application.include_router(users.router)
    application.include_router(invites.router)
    application.include_router(lists.router)
    application.include_router(gifts.router)
    application.include_router(shares.router)
    application.include_router(connections.router)
    application.include_router(collections_.router)
    application.include_router(meta.router)
    application.include_router(family_invites.router)
    application.include_router(families.router)

    @application.get("/health")
    def health():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"status": "healthy"}
        except Exception:
            return {"status": "unhealthy"}, 503

    return application


app = create_app()
