from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.family_invites import service as invite_service
from app.models.family_invite import FamilyInvite
from app.schemas.family_invite import (
    FamilyInviteCreate,
    FamilyInviteRead,
    IncomingFamilyInviteRead,
)
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

router = APIRouter(prefix="/families", tags=["family-invites"])


@router.get("/invites", response_model=list[IncomingFamilyInviteRead])
def list_incoming_invites(user: CurrentUser, db: DbSession):
    return invite_service.list_incoming_invites(db, actor=user)


@router.post(
    "/{family_id}/invites",
    response_model=FamilyInviteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invite(
    family_id: int, request: FamilyInviteCreate, user: CurrentUser, db: DbSession
) -> FamilyInvite:
    try:
        return invite_service.create_invite(
            db,
            family_id=family_id,
            actor=user,
            email=request.email,
            role=request.role,
            simple_mode=request.simple_mode,
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.get("/{family_id}/invites", response_model=list[FamilyInviteRead])
def list_invites(family_id: int, user: CurrentUser, db: DbSession) -> list[FamilyInvite]:
    try:
        return invite_service.list_invites(db, family_id=family_id, actor=user)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.delete(
    "/{family_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT
)
def revoke_invite(
    family_id: int, invite_id: int, user: CurrentUser, db: DbSession
) -> None:
    try:
        invite_service.revoke_invite(
            db, family_id=family_id, invite_id=invite_id, actor=user
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.post(
    "/invites/{token}/decline", status_code=status.HTTP_204_NO_CONTENT
)
def decline_invite(token: str, user: CurrentUser, db: DbSession) -> None:
    try:
        invite_service.decline_invite(db, token=token, actor=user)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.post("/invites/{token}/accept")
def accept_invite(token: str, user: CurrentUser, db: DbSession) -> dict:
    try:
        return invite_service.accept_invite(db, token=token, actor=user)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
