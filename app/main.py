from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.auth import router as auth
from app.users import router as users
from app.invites import router as invites
from app.lists import router as lists
from app.gifts import router as gifts
from app.shares import router as shares
from app.connections import router as connections
from app.collections import router as collections_
from app.meta import router as meta


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
    application.include_router(shares.router)
    application.include_router(connections.router)
    application.include_router(collections_.router)
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
