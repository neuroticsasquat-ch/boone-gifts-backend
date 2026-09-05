from fastapi import APIRouter, HTTPException, Query, Response, status

from app.dependencies import CurrentUser, DbSession, OwnedList
from app.list_families import service as list_family_service
from app.schemas.list_family_share import ListFamilyShareState
from app.services.exceptions import ConflictError, ForbiddenError

router = APIRouter(prefix="/lists/{list_id}/families", tags=["list-families"])


@router.get("", response_model=list[ListFamilyShareState])
def list_family_shares(gift_list: OwnedList, db: DbSession):
    return list_family_service.list_family_states(db, gift_list)


@router.put("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
def share_with_family(
    family_id: int, gift_list: OwnedList, user: CurrentUser, db: DbSession
):
    try:
        list_family_service.create_grant(db, gift_list, family_id, user)
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
def unshare_from_family(
    family_id: int,
    gift_list: OwnedList,
    user: CurrentUser,
    db: DbSession,
    claims: str | None = Query(default=None, pattern="^(release|keep)$"),
):
    try:
        list_family_service.revoke_grant(db, gift_list, family_id, user, claims=claims)
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
