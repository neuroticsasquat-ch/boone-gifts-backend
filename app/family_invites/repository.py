from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.family_invite import FamilyInvite
from app.models.user import User


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()


def find_unaccepted_invite_by_email(
    db: Session, family_id: int, email: str
) -> FamilyInvite | None:
    return (
        db.execute(
            select(FamilyInvite)
            .where(
                FamilyInvite.family_id == family_id,
                FamilyInvite.email == email,
                FamilyInvite.accepted_at.is_(None),
            )
            .order_by(FamilyInvite.created_at.desc())
        )
        .scalars()
        .first()
    )


def create_invite(
    db: Session,
    *,
    family_id: int,
    email: str,
    role: str,
    simple_mode: bool,
    token: str,
    expires_at: datetime,
    invited_by_id: int,
) -> FamilyInvite:
    invite = FamilyInvite(
        family_id=family_id,
        email=email,
        role=role,
        simple_mode=simple_mode,
        token=token,
        expires_at=expires_at,
        invited_by_id=invited_by_id,
    )
    db.add(invite)
    db.flush()
    return invite


def list_pending_invites(db: Session, family_id: int) -> list[FamilyInvite]:
    return list(
        db.execute(
            select(FamilyInvite)
            .where(
                FamilyInvite.family_id == family_id,
                FamilyInvite.accepted_at.is_(None),
            )
            .order_by(FamilyInvite.created_at.desc())
        )
        .scalars()
        .all()
    )


def get_invite(db: Session, invite_id: int) -> FamilyInvite | None:
    return db.get(FamilyInvite, invite_id)


def delete_invite(db: Session, invite: FamilyInvite) -> None:
    db.delete(invite)
    db.flush()
