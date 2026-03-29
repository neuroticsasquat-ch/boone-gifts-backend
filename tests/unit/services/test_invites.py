from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.invites import service
from app.models.invite import Invite
from app.services.exceptions import NotFoundError


def _make_invite(
    id: int = 1,
    email: str = "invitee@test.com",
    role: str = "member",
    expires_in_days: int = 7,
    invited_by_id: int = 1,
) -> MagicMock:
    invite = MagicMock(spec=Invite)
    invite.id = id
    invite.email = email
    invite.role = role
    invite.expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    invite.invited_by_id = invited_by_id
    invite.token = "abc-123"
    invite.used_at = None
    invite.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return invite


REPO = "app.invites.service.repo"


# --- create_invite ---


@patch(f"{REPO}.create_invite")
def test_create_invite(mock_create):
    db = MagicMock()
    invite = _make_invite()
    mock_create.return_value = invite

    result = service.create_invite(
        db,
        email="invitee@test.com",
        role="member",
        expires_in_days=7,
        invited_by_id=1,
    )

    mock_create.assert_called_once_with(
        db, "invitee@test.com", "member", 7, 1
    )
    assert result.email == "invitee@test.com"
    assert result.role == "member"
    assert result.invited_by_id == 1


@patch(f"{REPO}.create_invite")
def test_create_invite_custom_expiration(mock_create):
    db = MagicMock()
    invite = _make_invite(expires_in_days=14)
    mock_create.return_value = invite

    result = service.create_invite(
        db,
        email="invitee@test.com",
        role="admin",
        expires_in_days=14,
        invited_by_id=2,
    )

    mock_create.assert_called_once_with(
        db, "invitee@test.com", "admin", 14, 2
    )
    assert result.expires_at > datetime.now(timezone.utc) + timedelta(days=13)


# --- list_invites ---


@patch(f"{REPO}.get_all_invites")
def test_list_invites(mock_get):
    db = MagicMock()
    invites = [_make_invite(id=1), _make_invite(id=2, email="other@test.com")]
    mock_get.return_value = invites

    result = service.list_invites(db)

    mock_get.assert_called_once_with(db)
    assert len(result) == 2


@patch(f"{REPO}.get_all_invites", return_value=[])
def test_list_invites_empty(mock_get):
    db = MagicMock()
    result = service.list_invites(db)
    assert result == []


# --- delete_invite ---


@patch(f"{REPO}.delete_invite")
@patch(f"{REPO}.find_invite_by_id")
def test_delete_invite(mock_find, mock_delete):
    db = MagicMock()
    invite = _make_invite(id=5)
    mock_find.return_value = invite

    service.delete_invite(db, invite_id=5)

    mock_find.assert_called_once_with(db, 5)
    mock_delete.assert_called_once_with(db, invite)


@patch(f"{REPO}.find_invite_by_id", return_value=None)
def test_delete_invite_not_found(mock_find):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.delete_invite(db, invite_id=999)
