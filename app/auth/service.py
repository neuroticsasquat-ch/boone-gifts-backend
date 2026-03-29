import jwt
from sqlalchemy.orm import Session

from app.auth import repository as repo
from app.config import settings
from app.dependencies import create_access_token, create_refresh_token
from app.services.exceptions import BadRequestError, UnauthorizedError


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
            token, or the user is inactive/missing.
    """
    try:
        payload = jwt.decode(
            refresh_token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError:
        raise UnauthorizedError()

    if payload.get("type") != "refresh":
        raise UnauthorizedError()

    user = repo.find_user_by_id(db, int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError()

    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
    }
