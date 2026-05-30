from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.connections.repository import find_accepted_connection_between
from app.database import SessionLocal
from app.models.collection import Collection
from app.models.user import User
from app.models.list_share import ListShare
from app.models.gift_list import GiftList


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]

security = HTTPBearer()


def create_access_token(user: User, *, iat: datetime | None = None) -> str:
    issued_at = iat or datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user: User, *, iat: datetime | None = None) -> str:
    issued_at = iat or datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "type": "refresh",
        "iat": issued_at,
        "exp": issued_at + timedelta(days=settings.refresh_token_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: DbSession,
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_iat": False},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if payload.get("type") == "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    iat = payload.get("iat")
    pwd_changed = user.password_changed_at
    if pwd_changed is not None and iat is not None:
        if pwd_changed.tzinfo is None:
            pwd_changed = pwd_changed.replace(tzinfo=timezone.utc)
        if int(pwd_changed.timestamp()) > int(iat):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return user


def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]


def get_list_for_owner(
    list_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: DbSession,
) -> GiftList:
    gift_list = db.get(GiftList, list_id)
    if gift_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if gift_list.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return gift_list


def get_list_for_viewer(
    list_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: DbSession,
) -> GiftList:
    gift_list = db.get(GiftList, list_id)
    if gift_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if gift_list.owner_id == user.id:
        return gift_list
    share = db.execute(
        select(ListShare).where(
            ListShare.list_id == list_id,
            ListShare.user_id == user.id,
        )
    ).scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return gift_list


OwnedList = Annotated[GiftList, Depends(get_list_for_owner)]
ViewableList = Annotated[GiftList, Depends(get_list_for_viewer)]


def require_connection(
    target_user_id: int,
    current_user: User,
    db: Session,
) -> None:
    connection = find_accepted_connection_between(db, current_user.id, target_user_id)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be connected to share a list with this user.",
        )


def get_collection_for_owner(
    collection_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: DbSession,
) -> Collection:
    """Load a collection and verify the current user owns it.

    Parameters:
        collection_id: The collection ID from the path.
        user: The authenticated user.
        db: Database session.

    Returns:
        The collection if found and owned by user.

    Raises:
        HTTPException: 404 if not found, 403 if not owner.
    """
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if collection.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return collection


OwnedCollection = Annotated[Collection, Depends(get_collection_for_owner)]
