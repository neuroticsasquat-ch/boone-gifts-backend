from fastapi import APIRouter, HTTPException, Query, Response, status

from app.dependencies import CurrentUser, DbSession, OwnedList
from app.list_occasions import service as list_occasion_service
from app.schemas.list_occasion_share import ShareTargetFamily
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

# The sharing control reads the families half at `/lists/{id}/families` and
# writes one occasion at a time, so the two roots are spelled out rather than
# carried by a prefix.
router = APIRouter(tags=["list-occasions"])


@router.get("/lists/{list_id}/families", response_model=list[ShareTargetFamily])
def list_share_targets(gift_list: OwnedList, db: DbSession):
    return list_occasion_service.list_share_targets(db, gift_list)


@router.put(
    "/lists/{list_id}/occasions/{occasion_id}", status_code=status.HTTP_204_NO_CONTENT
)
def share_with_occasion(
    occasion_id: int, gift_list: OwnedList, user: CurrentUser, db: DbSession
):
    try:
        list_occasion_service.create_share(db, gift_list, occasion_id, user)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/lists/{list_id}/occasions/{occasion_id}", status_code=status.HTTP_204_NO_CONTENT
)
def unshare_from_occasion(
    occasion_id: int,
    gift_list: OwnedList,
    user: CurrentUser,
    db: DbSession,
    claims: str | None = Query(default=None, pattern="^(release|keep)$"),
):
    try:
        list_occasion_service.revoke_share(
            db, gift_list, occasion_id, user, claims=claims
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
