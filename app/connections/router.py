from fastapi import APIRouter, HTTPException, status

from app.connections import service as connection_service
from app.dependencies import CurrentUser, DbSession
from app.schemas.connection import ConnectionCreate, ConnectionRead
from app.schemas.gift_list import GiftListRead
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)

router = APIRouter(prefix="/connections", tags=["connections"])


@router.post("", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(
    request: ConnectionCreate, user: CurrentUser, db: DbSession
) -> dict:
    try:
        return connection_service.create_connection(
            db,
            requester_id=user.id,
            target_user_id=request.user_id,
            target_email=request.email,
        )
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.get("", response_model=list[ConnectionRead])
def list_connections(user: CurrentUser, db: DbSession) -> list[dict]:
    return connection_service.list_connections(db, user.id)


@router.get("/requests", response_model=list[ConnectionRead])
def list_requests(user: CurrentUser, db: DbSession) -> list[dict]:
    return connection_service.list_requests(db, user.id)


@router.post("/{connection_id}/accept", response_model=ConnectionRead)
def accept_connection(connection_id: int, user: CurrentUser, db: DbSession) -> dict:
    try:
        return connection_service.accept_connection(db, connection_id, user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: int, user: CurrentUser, db: DbSession) -> None:
    try:
        connection_service.delete_connection(db, connection_id, user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.get("/{connection_id}/lists", response_model=list[GiftListRead])
def connection_lists(connection_id: int, user: CurrentUser, db: DbSession):
    try:
        return connection_service.get_connection_lists(db, connection_id, user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
