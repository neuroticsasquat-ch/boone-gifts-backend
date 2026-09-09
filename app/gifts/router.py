from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession, OwnedList, ViewableList
from app.gifts import service as gift_service
from app.schemas.claim import ClaimCreate, PurchaseCreate
from app.schemas.gift import GiftCreate, GiftUpdate
from app.schemas.gift_list import GiftClaimRead, GiftOwnerRead, GiftRead
from app.services.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError

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


@router.post(
    "/{gift_id}/claim",
    response_model=GiftClaimRead,
    status_code=status.HTTP_201_CREATED,
)
def claim_gift(
    gift_id: int,
    gift_list: ViewableList,
    user: CurrentUser,
    db: DbSession,
    request: ClaimCreate | None = None,
):
    # The body is optional, and an omitted `occasion_id` differs from an explicit
    # null: the first asks the server to resolve the filing, the second is the
    # claimer filing under nothing. `model_fields_set` is the only thing that
    # tells them apart once the body is parsed.
    occasion_provided = request is not None and "occasion_id" in request.model_fields_set
    try:
        return gift_service.claim_gift(
            db,
            gift_id,
            gift_list.id,
            gift_list.owner_id,
            user,
            occasion_id=request.occasion_id if request else None,
            occasion_provided=occasion_provided,
        )
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
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
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.post("/{gift_id}/purchase", response_model=GiftRead)
def purchase_gift(
    gift_id: int,
    gift_list: ViewableList,
    user: CurrentUser,
    db: DbSession,
    request: PurchaseCreate | None = None,
):
    # The body is optional: ticking purchased without recording an amount is
    # the "Skip" the spec asks for, not a malformed request.
    updates = request.model_dump(exclude_unset=True) if request else {}
    try:
        return gift_service.purchase_gift(db, gift_id, gift_list.id, user.id, updates)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.delete("/{gift_id}/purchase", response_model=GiftRead)
def unpurchase_gift(
    gift_id: int, gift_list: ViewableList, user: CurrentUser, db: DbSession
):
    try:
        return gift_service.unpurchase_gift(db, gift_id, gift_list.id, user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
