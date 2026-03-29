from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.invite import Invite


def create_invite(
    db: Session,
    email: str,
    role: str,
    expires_in_days: int,
    invited_by_id: int,
) -> Invite:
    invite = Invite(
        email=email,
        role=role,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        invited_by_id=invited_by_id,
    )
    db.add(invite)
    db.flush()
    return invite


def get_all_invites(db: Session) -> list[Invite]:
    return db.execute(select(Invite)).scalars().all()


def find_invite_by_id(db: Session, invite_id: int) -> Invite | None:
    return db.get(Invite, invite_id)


def delete_invite(db: Session, invite: Invite) -> None:
    db.delete(invite)
    db.flush()
