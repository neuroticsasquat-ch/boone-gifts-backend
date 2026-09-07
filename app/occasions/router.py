from fastapi import APIRouter, HTTPException, Query, status

from app.occasions import service as occasion_service
from app.dependencies import CurrentUser, DbSession, OwnedOccasion
from app.schemas.occasion import (
    OccasionCreate,
    OccasionDetail,
    OccasionItemCreate,
    OccasionRead,
    OccasionUpdate,
    ShoppingListItem,
)
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

router = APIRouter(prefix="/occasions", tags=["occasions"])


@router.post("", response_model=OccasionRead, status_code=status.HTTP_201_CREATED)
def create_occasion(request: OccasionCreate, user: CurrentUser, db: DbSession):
    return occasion_service.create_occasion(
        db, name=request.name, description=request.description, owner_id=user.id
    )


@router.get("", response_model=list[OccasionRead])
def list_occasions(user: CurrentUser, db: DbSession, archived: bool = Query(default=False)):
    return occasion_service.list_occasions(db, owner_id=user.id, archived=archived)


@router.get("/for-list/{list_id}", response_model=list[int])
def occasions_for_list(list_id: int, user: CurrentUser, db: DbSession):
    return occasion_service.get_occasion_ids_for_list(db, list_id, user.id)


@router.get("/{occasion_id}", response_model=OccasionDetail)
def get_occasion(occasion: OwnedOccasion, db: DbSession):
    return occasion_service.get_occasion_detail(db, occasion)


@router.put("/{occasion_id}", response_model=OccasionRead)
def update_occasion(
    request: OccasionUpdate, occasion: OwnedOccasion, db: DbSession
):
    update_data = request.model_dump(exclude_unset=True)
    return occasion_service.update_occasion(db, occasion, update_data)


@router.delete("/{occasion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_occasion(occasion: OwnedOccasion, db: DbSession):
    occasion_service.delete_occasion(db, occasion)


@router.post(
    "/{occasion_id}/items",
    status_code=status.HTTP_201_CREATED,
)
def add_item(
    request: OccasionItemCreate,
    occasion: OwnedOccasion,
    user: CurrentUser,
    db: DbSession,
):
    try:
        occasion_service.add_item(
            db, occasion=occasion, list_id=request.list_id, user=user
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.delete(
    "/{occasion_id}/items/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_item(list_id: int, occasion: OwnedOccasion, db: DbSession):
    try:
        occasion_service.remove_item(db, occasion=occasion, list_id=list_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.get("/{occasion_id}/shopping-list", response_model=list[ShoppingListItem])
def get_shopping_list(occasion: OwnedOccasion, user: CurrentUser, db: DbSession):
    return occasion_service.get_shopping_list(db, occasion.id, user.id)
