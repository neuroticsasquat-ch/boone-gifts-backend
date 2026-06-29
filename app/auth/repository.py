from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.invite import Invite
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def find_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(
    db: Session, email: str, name: str, role: str, password: str, simple_mode: bool = False
) -> User:
    user = User(
        email=email,
        name=name,
        role=role,
        password_hash="",
        simple_mode=simple_mode,
    )
    user.set_password(password)
    db.add(user)
    db.flush()
    return user


def find_invite_by_token(db: Session, token: str) -> Invite | None:
    return db.execute(select(Invite).where(Invite.token == token)).scalar_one_or_none()


def mark_invite_used(db: Session, invite: Invite) -> None:
    invite.used_at = datetime.now(timezone.utc)
    db.flush()


def create_password_reset_token(
    db: Session, user_id: int, token_hash: str, expires_at: datetime
) -> PasswordResetToken:
    token = PasswordResetToken(
        user_id=user_id, token_hash=token_hash, expires_at=expires_at
    )
    db.add(token)
    db.flush()
    return token


def find_password_reset_token(db: Session, token_hash: str) -> PasswordResetToken | None:
    return db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    ).scalar_one_or_none()


def mark_password_reset_token_used(db: Session, token: PasswordResetToken) -> None:
    token.used_at = datetime.now(timezone.utc)
    db.flush()


def update_user_password(db: Session, user: User, new_password: str) -> None:
    user.set_password(new_password)
    # +1s buffer so tokens issued in the same wall-clock second as the reset
    # (JWT iat is integer seconds) are reliably invalidated by the iat-vs-
    # password_changed_at check in dependencies.get_current_user / auth.refresh.
    user.password_changed_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    db.flush()
