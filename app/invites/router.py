from fastapi import APIRouter, HTTPException, status

from app.dependencies import AdminUser, DbSession
from app.invites import service as invite_service
from app.schemas.invite import InviteCreate, InviteRead
from app.services.exceptions import NotFoundError

router = APIRouter(prefix="/invites", tags=["invites"])


@router.post("", response_model=InviteRead, status_code=status.HTTP_201_CREATED)
def create_invite(request: InviteCreate, admin: AdminUser, db: DbSession):
    return invite_service.create_invite(
        db,
        email=request.email,
        role=request.role,
        expires_in_days=request.expires_in_days,
        invited_by_id=admin.id,
    )


@router.get("", response_model=list[InviteRead])
def list_invites(admin: AdminUser, db: DbSession):
    return invite_service.list_invites(db)


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invite(invite_id: int, admin: AdminUser, db: DbSession):
    try:
        invite_service.delete_invite(db, invite_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
