from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, OwnedList
from app.schemas.list_share import ListShareCreate, ListShareRead
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.shares import service as share_service

router = APIRouter(prefix="/lists/{list_id}/shares", tags=["shares"])


@router.post("", response_model=ListShareRead, status_code=status.HTTP_201_CREATED)
def create_share(
    request: ListShareCreate, gift_list: OwnedList, user: CurrentUser, db: DbSession
):
    try:
        return share_service.create_share(
            db,
            list_id=gift_list.id,
            user_id=request.user_id,
            current_user_id=user.id,
        )
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.get("", response_model=list[ListShareRead])
def list_shares(gift_list: OwnedList, db: DbSession):
    return share_service.list_shares(db, list_id=gift_list.id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_share(user_id: int, gift_list: OwnedList, db: DbSession):
    try:
        share_service.delete_share(db, list_id=gift_list.id, user_id=user_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
