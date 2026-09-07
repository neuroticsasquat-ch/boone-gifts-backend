from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.account import service as account_service
from app.dependencies import CurrentUser, DbSession
from app.schemas.account import AccountConflict, AccountRead, AccountUpdate
from app.services.exceptions import BadRequestError, NotFoundError

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountRead)
def get_account(user: CurrentUser, db: DbSession):
    return account_service.get_account(db, user)


@router.put(
    "",
    response_model=AccountRead,
    responses={status.HTTP_409_CONFLICT: {"model": AccountConflict}},
)
def replace_account(
    request: AccountUpdate,
    user: CurrentUser,
    db: DbSession,
    confirm: bool = Query(default=False),
):
    try:
        return account_service.replace_account(db, user, request, confirm=confirm)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except account_service.LabelsWouldBeStripped as e:
        # A bare `{"affected_lists": N}` body rather than this API's usual
        # `{"detail": ...}`: the count is the whole point of the 409 and the
        # client reads it directly to write the confirmation prompt (spec §3.1).
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=AccountConflict(affected_lists=e.affected_lists).model_dump(),
        )
