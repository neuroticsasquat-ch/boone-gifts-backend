from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.auth import service
from app.config import settings
from app.models.invite import Invite
from app.models.user import User
from app.services.exceptions import BadRequestError, UnauthorizedError


def _make_user(
    id: int = 1,
    email: str = "user@test.com",
    name: str = "Test User",
    role: str = "member",
    is_active: bool = True,
) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = id
    user.email = email
    user.name = name
    user.role = role
    user.is_active = is_active
    return user


def _make_invite(
    token: str = "valid-token",
    email: str = "invite@test.com",
    role: str = "member",
    is_valid: bool = True,
) -> MagicMock:
    invite = MagicMock(spec=Invite)
    invite.token = token
    invite.email = email
    invite.role = role
    invite.is_valid = is_valid
    return invite


def _make_refresh_token(user_id: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": datetime(2099, 1, 1, tzinfo=timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _make_access_token(user_id: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "email": "user@test.com",
        "role": "member",
        "exp": datetime(2099, 1, 1, tzinfo=timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


REPO = "app.auth.service.repo"


# --- login ---


@patch(f"{REPO}.find_user_by_email")
def test_login_success(mock_find):
    db = MagicMock()
    user = _make_user()
    user.check_password.return_value = True
    mock_find.return_value = user

    result = service.login(db, "user@test.com", "password123")

    mock_find.assert_called_once_with(db, "user@test.com")
    user.check_password.assert_called_once_with("password123")
    assert "access_token" in result
    assert "refresh_token" in result


@patch(f"{REPO}.find_user_by_email")
def test_login_wrong_password(mock_find):
    db = MagicMock()
    user = _make_user()
    user.check_password.return_value = False
    mock_find.return_value = user

    with pytest.raises(UnauthorizedError):
        service.login(db, "user@test.com", "wrong-password")


@patch(f"{REPO}.find_user_by_email", return_value=None)
def test_login_user_not_found(mock_find):
    db = MagicMock()

    with pytest.raises(UnauthorizedError):
        service.login(db, "nobody@test.com", "password123")


@patch(f"{REPO}.find_user_by_email")
def test_login_inactive_user(mock_find):
    db = MagicMock()
    user = _make_user(is_active=False)
    user.check_password.return_value = True
    mock_find.return_value = user

    with pytest.raises(UnauthorizedError):
        service.login(db, "user@test.com", "password123")


# --- register ---


@patch(f"{REPO}.mark_invite_used")
@patch(f"{REPO}.create_user")
@patch(f"{REPO}.find_invite_by_token")
def test_register_success(mock_find_invite, mock_create_user, mock_mark_used):
    db = MagicMock()
    invite = _make_invite()
    mock_find_invite.return_value = invite
    user = _make_user(email="invite@test.com")
    mock_create_user.return_value = user

    result = service.register(db, "valid-token", "New User", "password123")

    mock_find_invite.assert_called_once_with(db, "valid-token")
    mock_create_user.assert_called_once_with(
        db,
        email="invite@test.com",
        name="New User",
        role="member",
        password="password123",
    )
    mock_mark_used.assert_called_once_with(db, invite)
    assert "access_token" in result
    assert "refresh_token" in result


@patch(f"{REPO}.find_invite_by_token")
def test_register_expired_invite(mock_find_invite):
    db = MagicMock()
    invite = _make_invite(is_valid=False)
    mock_find_invite.return_value = invite

    with pytest.raises(BadRequestError, match="Invalid or expired invite"):
        service.register(db, "expired-token", "New User", "password123")


@patch(f"{REPO}.find_invite_by_token")
def test_register_used_invite(mock_find_invite):
    db = MagicMock()
    invite = _make_invite(is_valid=False)
    mock_find_invite.return_value = invite

    with pytest.raises(BadRequestError, match="Invalid or expired invite"):
        service.register(db, "used-token", "New User", "password123")


@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_register_invalid_invite_token(mock_find_invite):
    db = MagicMock()

    with pytest.raises(BadRequestError, match="Invalid or expired invite"):
        service.register(db, "nonexistent-token", "New User", "password123")


# --- refresh ---


@patch(f"{REPO}.find_user_by_id")
def test_refresh_success(mock_find):
    db = MagicMock()
    user = _make_user()
    mock_find.return_value = user
    token = _make_refresh_token(user_id=1)

    result = service.refresh(db, token)

    mock_find.assert_called_once_with(db, 1)
    assert "access_token" in result
    assert "refresh_token" in result


def test_refresh_with_access_token_fails():
    db = MagicMock()
    token = _make_access_token(user_id=1)

    with pytest.raises(UnauthorizedError):
        service.refresh(db, token)


def test_refresh_invalid_token():
    db = MagicMock()

    with pytest.raises(UnauthorizedError):
        service.refresh(db, "not-a-valid-jwt")


@patch(f"{REPO}.find_user_by_id", return_value=None)
def test_refresh_user_not_found(mock_find):
    db = MagicMock()
    token = _make_refresh_token(user_id=999)

    with pytest.raises(UnauthorizedError):
        service.refresh(db, token)


@patch(f"{REPO}.find_user_by_id")
def test_refresh_inactive_user(mock_find):
    db = MagicMock()
    user = _make_user(is_active=False)
    mock_find.return_value = user
    token = _make_refresh_token(user_id=1)

    with pytest.raises(UnauthorizedError):
        service.refresh(db, token)
