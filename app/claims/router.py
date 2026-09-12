from fastapi import APIRouter, HTTPException, status

from app.claims import service as claim_service
from app.dependencies import CurrentUser, DbSession
from app.schemas.claim import ClaimRead, ClaimUpdate
from app.services.exceptions import ForbiddenError

router = APIRouter(prefix="/claims", tags=["claims"])


@router.patch("/{claim_id}", response_model=ClaimRead)
def update_claim(
    claim_id: int, updates: ClaimUpdate, user: CurrentUser, db: DbSession
):
    # No 404 arm: a claim that does not exist answers 403 like anyone else's,
    # so the list's owner learns nothing by probing ids.
    try:
        return claim_service.update_claim(
            db, claim_id, user, updates.model_dump(exclude_unset=True)
        )
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
