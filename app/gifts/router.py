from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, OwnedList, ViewableList
from app.gifts import service as gift_service
from app.schemas.gift import GiftCreate, GiftUpdate
from app.schemas.gift_list import GiftOwnerRead, GiftRead
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

router = APIRouter(prefix="/lists/{list_id}/gifts", tags=["gifts"])


@router.post("", response_model=GiftOwnerRead, status_code=status.HTTP_201_CREATED)
def create_gift(request: GiftCreate, gift_list: OwnedList, db: DbSession):
    return gift_service.create_gift(
        db,
        list_id=gift_list.id,
        name=request.name,
        description=request.description,
        url=request.url,
        price=request.price,
    )


@router.put("/{gift_id}", response_model=GiftOwnerRead)
def update_gift(gift_id: int, updates: GiftUpdate, gift_list: OwnedList, db: DbSession):
    try:
        return gift_service.update_gift(
            db, gift_id, gift_list.id, updates.model_dump(exclude_unset=True)
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.delete("/{gift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gift(gift_id: int, gift_list: OwnedList, db: DbSession):
    try:
        gift_service.delete_gift(db, gift_id, gift_list.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{gift_id}/claim", response_model=GiftRead)
def claim_gift(gift_id: int, gift_list: ViewableList, user: CurrentUser, db: DbSession):
    try:
        return gift_service.claim_gift(
            db, gift_id, gift_list.id, gift_list.owner_id, user.id
        )
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.delete("/{gift_id}/claim", response_model=GiftRead)
def unclaim_gift(
    gift_id: int, gift_list: ViewableList, user: CurrentUser, db: DbSession
):
    try:
        return gift_service.unclaim_gift(db, gift_id, gift_list.id, user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
