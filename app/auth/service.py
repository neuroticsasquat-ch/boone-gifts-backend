import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from app.auth import repository as repo
from app.config import settings
from app.dependencies import create_access_token, create_refresh_token
from app.email import send_email
from app.email.password_reset import render_password_reset_email
from app.services.exceptions import BadRequestError, UnauthorizedError

logger = logging.getLogger(__name__)

PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)


def login(db: Session, email: str, password: str) -> dict:
    """Validate credentials and return access + refresh tokens.

    Raises:
        UnauthorizedError: If user not found, wrong password, or inactive.
    """
    user = repo.find_user_by_email(db, email)

    if user is None or not user.check_password(password):
        raise UnauthorizedError()

    if not user.is_active:
        raise UnauthorizedError()

    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
    }


def register(db: Session, token: str, name: str, password: str) -> dict:
    """Register a new user with an invite token.

    Raises:
        BadRequestError: If the invite token is invalid, expired, or used.
    """
    invite = repo.find_invite_by_token(db, token)

    if invite is None or not invite.is_valid:
        raise BadRequestError("Invalid or expired invite.")

    user = repo.create_user(
        db,
        email=invite.email,
        name=name,
        role=invite.role,
        password=password,
    )

    repo.mark_invite_used(db, invite)

    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
    }


def refresh(db: Session, refresh_token: str) -> dict:
    """Validate a refresh token and return new access + refresh tokens.

    Raises:
        UnauthorizedError: If the token is missing, invalid, not a refresh
            token, the user is inactive/missing, or the token was issued
            before the user's last password change.
    """
    try:
        payload = jwt.decode(
            refresh_token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_iat": False},
        )
    except jwt.InvalidTokenError:
        raise UnauthorizedError()

    if payload.get("type") != "refresh":
        raise UnauthorizedError()

    user = repo.find_user_by_id(db, int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError()

    if _token_invalidated_by_password_change(payload, user.password_changed_at):
        raise UnauthorizedError()

    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
    }


def forgot_password(db: Session, email: str) -> None:
    """Issue and email a password reset token if the email matches a user.

    Always succeeds silently to avoid user enumeration. Email failures are
    logged but do not surface to the caller.
    """
    user = repo.find_user_by_email(db, email)
    if user is None or not user.is_active:
        return

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw_token)
    expires_at = datetime.now(timezone.utc) + PASSWORD_RESET_TOKEN_TTL
    repo.create_password_reset_token(db, user.id, token_hash, expires_at)

    subject, html, text = render_password_reset_email(
        token=raw_token,
        expires_at=expires_at,
        frontend_url=settings.frontend_url,
    )
    try:
        send_email(to=user.email, subject=subject, html=html, text=text)
    except Exception:
        logger.exception("Failed to send password reset email to %s", user.email)


def change_password(
    db: Session, user, current_password: str, new_password: str
) -> dict:
    """Change a logged-in user's password and issue fresh tokens.

    Raises:
        BadRequestError: If current_password does not match.
    """
    if not user.check_password(current_password):
        raise BadRequestError("Current password is incorrect.")

    repo.update_user_password(db, user, new_password)

    # iat=password_changed_at so the freshly-issued tokens pass the
    # `password_changed_at > iat` invalidation check on subsequent requests.
    return {
        "access_token": create_access_token(user, iat=user.password_changed_at),
        "refresh_token": create_refresh_token(user, iat=user.password_changed_at),
    }


def reset_password(db: Session, raw_token: str, new_password: str) -> None:
    """Consume a password reset token and update the user's password.

    Raises:
        BadRequestError: If the token is missing, expired, or already used.
    """
    token_hash = _hash_reset_token(raw_token)
    token = repo.find_password_reset_token(db, token_hash)

    if token is None or token.used_at is not None:
        raise BadRequestError("Invalid or expired reset token.")

    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise BadRequestError("Invalid or expired reset token.")

    user = repo.find_user_by_id(db, token.user_id)
    if user is None or not user.is_active:
        raise BadRequestError("Invalid or expired reset token.")

    repo.update_user_password(db, user, new_password)
    repo.mark_password_reset_token_used(db, token)


def _hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _token_invalidated_by_password_change(
    payload: dict, password_changed_at: datetime | None
) -> bool:
    if password_changed_at is None:
        return False
    iat = payload.get("iat")
    if iat is None:
        return True
    if password_changed_at.tzinfo is None:
        password_changed_at = password_changed_at.replace(tzinfo=timezone.utc)
    return int(password_changed_at.timestamp()) > int(iat)
