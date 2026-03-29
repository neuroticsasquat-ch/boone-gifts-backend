from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.invite import Invite
from app.models.user import User


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()


def find_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, email: str, name: str, role: str, password: str) -> User:
    user = User(
        email=email,
        name=name,
        role=role,
        password_hash="",
    )
    user.set_password(password)
    db.add(user)
    db.flush()
    return user


def find_invite_by_token(db: Session, token: str) -> Invite | None:
    return db.execute(
        select(Invite).where(Invite.token == token)
    ).scalar_one_or_none()


def mark_invite_used(db: Session, invite: Invite) -> None:
    invite.used_at = datetime.now(timezone.utc)
    db.flush()
