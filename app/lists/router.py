from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.dependencies import CurrentUser, DbSession, OwnedList, ViewableList
from app.lists import service as list_service
from app.schemas.gift_list import GiftListCreate, GiftListRead, GiftListUpdate
from app.services.exceptions import ConflictError

router = APIRouter(prefix="/lists", tags=["lists"])


class UnseenCountResponse(BaseModel):
    count: int


@router.post("", response_model=GiftListRead, status_code=status.HTTP_201_CREATED)
def create_list(request: GiftListCreate, user: CurrentUser, db: DbSession):
    return list_service.create_list(
        db, name=request.name, description=request.description, owner_id=user.id
    )


@router.get("", response_model=list[GiftListRead])
def list_lists(
    user: CurrentUser,
    db: DbSession,
    filter: str | None = Query(default=None, pattern="^(owned|shared|family)$"),
    archived: bool = Query(default=False),
):
    return list_service.get_lists(db, user_id=user.id, filter=filter, archived=archived)


@router.get("/unseen-count", response_model=UnseenCountResponse)
def unseen_share_count(user: CurrentUser, db: DbSession):
    count = list_service.get_unseen_share_count(db, user_id=user.id)
    return UnseenCountResponse(count=count)


@router.get("/{list_id}")
def get_list(gift_list: ViewableList, user: CurrentUser, db: DbSession):
    if gift_list.owner_id != user.id:
        list_service.mark_share_seen(db, list_id=gift_list.id, user_id=user.id)
    return list_service.get_list(gift_list, user_id=user.id)


@router.put("/{list_id}", response_model=GiftListRead)
def update_list(updates: GiftListUpdate, gift_list: OwnedList, db: DbSession):
    return list_service.update_list(
        db, gift_list, updates=updates.model_dump(exclude_unset=True)
    )


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(gift_list: OwnedList, db: DbSession):
    try:
        list_service.delete_list(db, gift_list)
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        )
