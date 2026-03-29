from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import auth, users, invites, lists, gifts, list_shares, connections, collections, meta


def create_app() -> FastAPI:
    application = FastAPI(title="Boone Gifts API")

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
    application.include_router(list_shares.router)
    application.include_router(connections.router)
    application.include_router(collections.router)
    application.include_router(meta.router)

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
