from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.invites import service
from app.models.invite import Invite


def _make_invite(token: str = "abc-123", email: str = "invitee@test.com") -> MagicMock:
    invite = MagicMock(spec=Invite)
    invite.id = 1
    invite.email = email
    invite.role = "member"
    invite.token = token
    invite.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    invite.invited_by_id = 1
    invite.used_at = None
    return invite


REPO = "app.invites.service.repo"
SEND_EMAIL = "app.invites.service.send_email"


@patch(SEND_EMAIL)
@patch(f"{REPO}.create_invite")
def test_create_invite_sends_email_to_invitee(mock_create, mock_send):
    invite = _make_invite(token="tok-xyz", email="someone@test.com")
    mock_create.return_value = invite

    service.create_invite(
        MagicMock(),
        email="someone@test.com",
        role="member",
        expires_in_days=7,
        invited_by_id=1,
    )

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to"] == "someone@test.com"
    assert "tok-xyz" in kwargs["html"]
    assert "tok-xyz" in kwargs["text"]


@patch(SEND_EMAIL)
@patch(f"{REPO}.create_invite")
def test_create_invite_returns_invite_when_email_fails(mock_create, mock_send):
    invite = _make_invite()
    mock_create.return_value = invite
    mock_send.side_effect = RuntimeError("smtp down")

    result = service.create_invite(
        MagicMock(),
        email="someone@test.com",
        role="member",
        expires_in_days=7,
        invited_by_id=1,
    )

    assert result is invite


@patch(SEND_EMAIL)
@patch(f"{REPO}.create_invite")
def test_create_invite_logs_when_email_fails(mock_create, mock_send, caplog):
    mock_create.return_value = _make_invite()
    mock_send.side_effect = RuntimeError("smtp down")

    with caplog.at_level("ERROR", logger="app.invites.service"):
        service.create_invite(
            MagicMock(),
            email="someone@test.com",
            role="member",
            expires_in_days=7,
            invited_by_id=1,
        )

    assert any("invite email" in r.message.lower() for r in caplog.records)
