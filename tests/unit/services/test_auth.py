from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.auth import service
from app.config import settings
from app.dependencies import create_access_token
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.invite import Invite
from app.models.user import User
from app.services.exceptions import BadRequestError, UnauthorizedError


def _make_user(
    id: int = 1,
    email: str = "user@test.com",
    name: str = "Test User",
    role: str = "member",
    is_active: bool = True,
    simple_mode: bool = False,
) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = id
    user.email = email
    user.name = name
    user.role = role
    user.is_active = is_active
    user.simple_mode = simple_mode
    user.password_changed_at = None
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


def _make_family_invite(
    family_id: int = 1,
    email: str = "newmember@test.com",
    role: str = "member",
    token: str = "fam-token",
    accepted_at: datetime | None = None,
    declined_at: datetime | None = None,
    expires_in_days: int = 7,
    simple_mode: bool = False,
) -> MagicMock:
    # spec=FamilyInvite makes unset attrs truthy mocks, so set accepted_at /
    # declined_at explicitly — _family_invite_registerable depends on them.
    invite = MagicMock(spec=FamilyInvite)
    invite.family_id = family_id
    invite.email = email
    invite.role = role
    invite.token = token
    invite.accepted_at = accepted_at
    invite.declined_at = declined_at
    invite.expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    invite.simple_mode = simple_mode
    return invite


def _make_family(id: int = 1, name: str = "Boone Family") -> MagicMock:
    family = MagicMock(spec=Family)
    family.id = id
    family.name = name
    return family


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
FAMILY_INVITES_REPO = "app.auth.service.family_invites_repo"
FAMILIES_REPO = "app.auth.service.families_repo"


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


@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token", return_value=None)
@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_register_invalid_invite_token(mock_find_invite, mock_find_family_invite):
    db = MagicMock()

    with pytest.raises(BadRequestError, match="Invalid or expired invite"):
        service.register(db, "nonexistent-token", "New User", "password123")


# --- register via family invite ---


@patch(f"{FAMILIES_REPO}.create_family_member")
@patch(f"{REPO}.create_user")
@patch(f"{REPO}.find_user_by_email", return_value=None)
@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token")
@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_register_family_invite_creates_member_and_membership(
    mock_find_admin,
    mock_get_family_invite,
    mock_find_user,
    mock_create_user,
    mock_create_member,
):
    db = MagicMock()
    # family role is organizer; app role must still be member (no escalation)
    invite = _make_family_invite(family_id=3, email="newmember@test.com", role="organizer")
    mock_get_family_invite.return_value = invite
    user = _make_user(id=42, email="newmember@test.com", role="member")
    mock_create_user.return_value = user

    result = service.register(db, "fam-token", "New Member", "password123")

    mock_create_user.assert_called_once_with(
        db,
        email="newmember@test.com",
        name="New Member",
        role="member",
        password="password123",
        simple_mode=False,
    )
    mock_create_member.assert_called_once_with(
        db, family_id=3, user_id=42, role="organizer"
    )
    assert invite.accepted_at is not None
    assert "access_token" in result
    assert "refresh_token" in result


@patch(f"{FAMILIES_REPO}.create_family_member")
@patch(f"{REPO}.create_user")
@patch(f"{REPO}.find_user_by_email", return_value=None)
@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token")
@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_register_family_invite_passes_simple_mode_true_to_create_user(
    mock_find_admin,
    mock_get_family_invite,
    mock_find_user,
    mock_create_user,
    mock_create_member,
):
    db = MagicMock()
    invite = _make_family_invite(simple_mode=True)
    mock_get_family_invite.return_value = invite
    mock_create_user.return_value = _make_user(simple_mode=True)

    service.register(db, "fam-token", "New Member", "password123")

    mock_create_user.assert_called_once_with(
        db,
        email=invite.email,
        name="New Member",
        role="member",
        password="password123",
        simple_mode=True,
    )


@patch(f"{FAMILIES_REPO}.create_family_member")
@patch(f"{REPO}.create_user")
@patch(f"{REPO}.find_user_by_email", return_value=None)
@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token")
@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_register_family_invite_passes_simple_mode_false_to_create_user(
    mock_find_admin,
    mock_get_family_invite,
    mock_find_user,
    mock_create_user,
    mock_create_member,
):
    db = MagicMock()
    invite = _make_family_invite(simple_mode=False)
    mock_get_family_invite.return_value = invite
    mock_create_user.return_value = _make_user(simple_mode=False)

    service.register(db, "fam-token", "New Member", "password123")

    mock_create_user.assert_called_once_with(
        db,
        email=invite.email,
        name="New Member",
        role="member",
        password="password123",
        simple_mode=False,
    )


@patch(f"{FAMILIES_REPO}.create_family_member")
@patch(f"{REPO}.create_user")
@patch(f"{REPO}.find_user_by_email")
@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token")
@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_register_family_invite_existing_account_rejected(
    mock_find_admin,
    mock_get_family_invite,
    mock_find_user,
    mock_create_user,
    mock_create_member,
):
    db = MagicMock()
    mock_get_family_invite.return_value = _make_family_invite(email="existing@test.com")
    mock_find_user.return_value = _make_user(email="existing@test.com")

    with pytest.raises(BadRequestError, match="account already exists"):
        service.register(db, "fam-token", "Dup", "password123")

    mock_create_user.assert_not_called()
    mock_create_member.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"accepted_at": datetime.now(timezone.utc)},
        {"declined_at": datetime.now(timezone.utc)},
        {"expires_in_days": -1},
    ],
)
@patch(f"{FAMILIES_REPO}.create_family_member")
@patch(f"{REPO}.create_user")
@patch(f"{REPO}.find_user_by_email", return_value=None)
@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token")
@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_register_family_invite_not_registerable(
    mock_find_admin,
    mock_get_family_invite,
    mock_find_user,
    mock_create_user,
    mock_create_member,
    kwargs,
):
    db = MagicMock()
    mock_get_family_invite.return_value = _make_family_invite(**kwargs)

    with pytest.raises(BadRequestError, match="Invalid or expired invite"):
        service.register(db, "fam-token", "X", "password123")

    mock_create_user.assert_not_called()
    mock_create_member.assert_not_called()


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


# --- invite_info ---


@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token")
@patch(f"{REPO}.find_invite_by_token")
def test_invite_info_admin_token(mock_find_admin, mock_get_family_invite):
    db = MagicMock()
    mock_find_admin.return_value = _make_invite(email="admin-invitee@test.com", is_valid=True)

    result = service.get_invite_info(db, "valid-token")

    assert result == {"email": "admin-invitee@test.com", "family_name": None}
    mock_get_family_invite.assert_not_called()


@patch(f"{REPO}.find_invite_by_token")
def test_invite_info_admin_invalid(mock_find_admin):
    db = MagicMock()
    mock_find_admin.return_value = _make_invite(is_valid=False)

    with pytest.raises(BadRequestError, match="Invalid or expired invite"):
        service.get_invite_info(db, "expired-token")


@patch(f"{FAMILIES_REPO}.get_family")
@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token")
@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_invite_info_family_token(mock_find_admin, mock_get_family_invite, mock_get_family):
    db = MagicMock()
    mock_get_family_invite.return_value = _make_family_invite(
        family_id=7, email="newmember@test.com"
    )
    mock_get_family.return_value = _make_family(id=7, name="Boone Family")

    result = service.get_invite_info(db, "fam-token")

    assert result == {"email": "newmember@test.com", "family_name": "Boone Family"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"accepted_at": datetime.now(timezone.utc)},
        {"declined_at": datetime.now(timezone.utc)},
        {"expires_in_days": -1},
    ],
)
@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token")
@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_invite_info_family_not_registerable(mock_find_admin, mock_get_family_invite, kwargs):
    db = MagicMock()
    mock_get_family_invite.return_value = _make_family_invite(**kwargs)

    with pytest.raises(BadRequestError, match="Invalid or expired invite"):
        service.get_invite_info(db, "fam-token")


@patch(f"{FAMILY_INVITES_REPO}.get_invite_by_token", return_value=None)
@patch(f"{REPO}.find_invite_by_token", return_value=None)
def test_invite_info_unknown_token(mock_find_admin, mock_get_family_invite):
    db = MagicMock()
    with pytest.raises(BadRequestError, match="Invalid or expired invite"):
        service.get_invite_info(db, "nope")


def test_family_invite_registerable_truth_table():
    assert service._family_invite_registerable(_make_family_invite()) is True
    assert (
        service._family_invite_registerable(
            _make_family_invite(accepted_at=datetime.now(timezone.utc))
        )
        is False
    )
    assert (
        service._family_invite_registerable(
            _make_family_invite(declined_at=datetime.now(timezone.utc))
        )
        is False
    )
    assert (
        service._family_invite_registerable(_make_family_invite(expires_in_days=-1))
        is False
    )


# --- create_access_token simple_mode claim ---


def test_create_access_token_includes_simple_mode_true():
    user = _make_user(simple_mode=True)
    token = create_access_token(user)
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_iat": False},
    )
    assert payload["simple_mode"] is True


def test_create_access_token_includes_simple_mode_false():
    user = _make_user(simple_mode=False)
    token = create_access_token(user)
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_iat": False},
    )
    assert payload["simple_mode"] is False


# --- update_profile simple_mode toggle ---


def test_update_profile_sets_simple_mode_when_provided():
    db = MagicMock()
    user = _make_user(simple_mode=False)
    service.update_profile(db, user, "Test Name", simple_mode=True)
    assert user.simple_mode is True


def test_update_profile_does_not_change_simple_mode_when_not_provided():
    db = MagicMock()
    user = _make_user(simple_mode=True)
    service.update_profile(db, user, "Test Name")
    assert user.simple_mode is True


def test_update_profile_clears_simple_mode_when_explicitly_false():
    db = MagicMock()
    user = _make_user(simple_mode=True)
    service.update_profile(db, user, "Test Name", simple_mode=False)
    assert user.simple_mode is False


def test_update_profile_simple_mode_only_preserves_name():
    db = MagicMock()
    user = _make_user(simple_mode=False)
    user.name = "Original Name"
    service.update_profile(db, user, simple_mode=True)
    assert user.simple_mode is True
    assert user.name == "Original Name"
