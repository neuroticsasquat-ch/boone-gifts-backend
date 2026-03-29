from sqlalchemy.orm import Session

from app.invites import repository as repo
from app.models.invite import Invite
from app.services.exceptions import NotFoundError


def create_invite(
    db: Session,
    email: str,
    role: str,
    expires_in_days: int,
    invited_by_id: int,
) -> Invite:
    return repo.create_invite(db, email, role, expires_in_days, invited_by_id)


def list_invites(db: Session) -> list[Invite]:
    return repo.get_all_invites(db)


def delete_invite(db: Session, invite_id: int) -> None:
    invite = repo.find_invite_by_id(db, invite_id)
    if invite is None:
        raise NotFoundError("Invite not found.")
    repo.delete_invite(db, invite)
