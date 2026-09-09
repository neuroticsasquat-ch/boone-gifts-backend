from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUser, DbSession
from app.occasions import service as occasion_service
from app.schemas.budget import BudgetRollup, BudgetWrite
from app.schemas.claim import ShoppingPayload
from app.schemas.occasion import (
    OccasionCreate,
    OccasionCreateRead,
    OccasionRead,
    OccasionUpdate,
)
from app.services.exceptions import ForbiddenError, NotFoundError

# Occasions live under two path roots — the family that owns them, and the
# occasion itself — so the paths are spelled out rather than carried by a prefix.
router = APIRouter(tags=["occasions"])


@router.get("/families/{family_id}/occasions", response_model=list[OccasionRead])
def list_occasions(
    family_id: int,
    user: CurrentUser,
    db: DbSession,
    archived: bool = Query(default=False),
):
    try:
        return occasion_service.list_occasions(
            db, family_id=family_id, actor=user, archived=archived
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.post(
    "/families/{family_id}/occasions",
    response_model=OccasionCreateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_occasion(
    family_id: int, request: OccasionCreate, user: CurrentUser, db: DbSession
):
    try:
        occasion, has_other_active = occasion_service.create_occasion(
            db, family_id=family_id, actor=user, name=request.name
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return OccasionCreateRead(
        **OccasionRead.model_validate(occasion).model_dump(),
        has_other_active=has_other_active,
    )


@router.get("/occasions/{occasion_id}", response_model=OccasionRead)
def get_occasion(occasion_id: int, user: CurrentUser, db: DbSession):
    try:
        return occasion_service.get_occasion(db, occasion_id=occasion_id, actor=user)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.put("/occasions/{occasion_id}", response_model=OccasionRead)
def update_occasion(
    occasion_id: int, request: OccasionUpdate, user: CurrentUser, db: DbSession
):
    try:
        return occasion_service.update_occasion(
            db,
            occasion_id=occasion_id,
            actor=user,
            update_data=request.model_dump(exclude_unset=True),
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


# No `response_model`: the service picks the schema per row, and declaring one
# here would re-widen owned rows or narrow viewer rows. See
# `app/lists/service.py:to_summary`.
@router.get("/occasions/{occasion_id}/lists")
def list_occasion_lists(occasion_id: int, user: CurrentUser, db: DbSession):
    try:
        return occasion_service.list_lists(db, occasion_id=occasion_id, actor=user)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.get("/occasions/{occasion_id}/shopping", response_model=ShoppingPayload)
def list_occasion_shopping(occasion_id: int, user: CurrentUser, db: DbSession):
    try:
        return occasion_service.list_shopping(db, occasion_id=occasion_id, actor=user)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


# Always the caller's own budget. There is no path here — and none anywhere —
# that names whose budget to read, which is what makes "no endpoint returns
# another user's spend" a shape rather than a promise.
@router.put("/occasions/{occasion_id}/budget", response_model=BudgetRollup)
def set_occasion_budget(
    occasion_id: int, request: BudgetWrite, user: CurrentUser, db: DbSession
):
    try:
        return occasion_service.set_budget(
            db, occasion_id=occasion_id, actor=user, amount=request.amount
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


# 200 with the rollup, not 204: the tab re-renders the same budget line with no
# target on it, and the counts beneath it are unchanged by the clearing.
@router.delete("/occasions/{occasion_id}/budget", response_model=BudgetRollup)
def clear_occasion_budget(occasion_id: int, user: CurrentUser, db: DbSession):
    try:
        return occasion_service.clear_budget(
            db, occasion_id=occasion_id, actor=user
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
