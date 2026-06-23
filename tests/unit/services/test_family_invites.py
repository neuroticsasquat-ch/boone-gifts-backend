from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.family_invites import service
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.family_member import FamilyMember
from app.models.user import User
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

REPO = "app.family_invites.service.repo"
FAMILIES_REPO = "app.family_invites.service.families_repo"
SEND_EMAIL = "app.family_invites.service.send_email"


def _make_user(id: int = 10, name: str = "Alice", email: str = "alice@test.com") -> MagicMock:
    user = MagicMock(spec=User)
    user.id = id
    user.name = name
    user.email = email
    return user


def _make_member(role: str = "organizer", user_id: int = 10, family_id: int = 1) -> MagicMock:
    member = MagicMock(spec=FamilyMember)
    member.role = role
    member.user_id = user_id
    member.family_id = family_id
    return member


def _make_family(id: int = 1, name: str = "Smith Family") -> MagicMock:
    family = MagicMock(spec=Family)
    family.id = id
    family.name = name
    return family


def _make_invite(
    id: int = 1,
    family_id: int = 1,
    email: str = "bob@test.com",
    token: str = "tok-123",
    accepted_at: datetime | None = None,
    declined_at: datetime | None = None,
    expires_in_days: int = 7,
    role: str = "member",
) -> MagicMock:
    invite = MagicMock(spec=FamilyInvite)
    invite.id = id
    invite.family_id = family_id
    invite.email = email
    invite.token = token
    invite.role = role
    invite.accepted_at = accepted_at
    invite.declined_at = declined_at
    invite.expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    return invite


@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# create_invite
# ---------------------------------------------------------------------------


@patch(SEND_EMAIL)
@patch(f"{REPO}.create_invite")
@patch(f"{REPO}.find_unaccepted_invite_by_email", return_value=None)
@patch(f"{REPO}.find_user_by_email", return_value=None)
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_create_invite_new_user(
    mock_get_family, mock_get_member, mock_find_user, mock_find_dup, mock_create, mock_send, db
):
    mock_get_family.return_value = _make_family(id=1, name="Smith Family")
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    invite = _make_invite(token="newtok", email="new@test.com")
    mock_create.return_value = invite
    actor = _make_user(id=10, name="Alice")

    result = service.create_invite(
        db, family_id=1, actor=actor, email="new@test.com", role="member", simple_mode=False
    )

    assert result is invite
    mock_create.assert_called_once()
    mock_send.assert_called_once()
    html = mock_send.call_args.kwargs["html"]
    assert "/register?family_invite=newtok" in html


@patch(SEND_EMAIL)
@patch(f"{REPO}.create_invite")
@patch(f"{REPO}.find_unaccepted_invite_by_email", return_value=None)
@patch(f"{REPO}.find_user_by_email")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_create_invite_existing_user_not_member(
    mock_get_family, mock_get_member, mock_find_user, mock_find_dup, mock_create, mock_send, db
):
    mock_get_family.return_value = _make_family(id=1, name="Smith Family")
    # 1st get_family_member = actor (organizer); 2nd = invitee lookup (not a member)
    mock_get_member.side_effect = [_make_member(role="organizer", user_id=10), None]
    mock_find_user.return_value = _make_user(id=20, name="Bob", email="bob@test.com")
    invite = _make_invite(token="botk", email="bob@test.com")
    mock_create.return_value = invite
    actor = _make_user(id=10, name="Alice")

    service.create_invite(
        db, family_id=1, actor=actor, email="bob@test.com", role="member", simple_mode=False
    )

    mock_create.assert_called_once()
    html = mock_send.call_args.kwargs["html"]
    assert "/family-invites/botk" in html


@patch(f"{REPO}.create_invite")
@patch(f"{REPO}.find_user_by_email")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_create_invite_already_member(
    mock_get_family, mock_get_member, mock_find_user, mock_create, db
):
    mock_get_family.return_value = _make_family()
    mock_get_member.side_effect = [
        _make_member(role="organizer", user_id=10),  # actor
        _make_member(role="member", user_id=20),  # invitee already a member
    ]
    mock_find_user.return_value = _make_user(id=20, email="bob@test.com")
    actor = _make_user(id=10)

    with pytest.raises(ConflictError):
        service.create_invite(
            db, family_id=1, actor=actor, email="bob@test.com", role="member", simple_mode=False
        )

    mock_create.assert_not_called()


@patch(f"{REPO}.create_invite")
@patch(f"{REPO}.find_unaccepted_invite_by_email")
@patch(f"{REPO}.find_user_by_email", return_value=None)
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_create_invite_duplicate_pending(
    mock_get_family, mock_get_member, mock_find_user, mock_find_dup, mock_create, db
):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    mock_find_dup.return_value = _make_invite(expires_in_days=3)  # not expired
    actor = _make_user(id=10)

    with pytest.raises(ConflictError):
        service.create_invite(
            db, family_id=1, actor=actor, email="new@test.com", role="member", simple_mode=False
        )

    mock_create.assert_not_called()


@patch(SEND_EMAIL)
@patch(f"{REPO}.create_invite")
@patch(f"{REPO}.delete_invite")
@patch(f"{REPO}.find_unaccepted_invite_by_email")
@patch(f"{REPO}.find_user_by_email", return_value=None)
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_create_invite_replaces_expired(
    mock_get_family, mock_get_member, mock_find_user, mock_find_dup, mock_delete, mock_create, mock_send, db
):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    expired = _make_invite(expires_in_days=-1)  # already expired
    mock_find_dup.return_value = expired
    mock_create.return_value = _make_invite(token="fresh")
    actor = _make_user(id=10)

    service.create_invite(
        db, family_id=1, actor=actor, email="new@test.com", role="member", simple_mode=False
    )

    mock_delete.assert_called_once_with(db, expired)
    mock_create.assert_called_once()


@patch(f"{REPO}.find_user_by_email")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_create_invite_not_organizer(mock_get_family, mock_get_member, mock_find_user, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="member", user_id=10)
    actor = _make_user(id=10)

    with pytest.raises(ForbiddenError, match="organizer"):
        service.create_invite(
            db, family_id=1, actor=actor, email="x@test.com", role="member", simple_mode=False
        )

    mock_find_user.assert_not_called()


@patch(f"{FAMILIES_REPO}.get_family", return_value=None)
def test_create_invite_family_not_found(mock_get_family, db):
    actor = _make_user(id=10)
    with pytest.raises(NotFoundError):
        service.create_invite(
            db, family_id=99, actor=actor, email="x@test.com", role="member", simple_mode=False
        )


@patch(SEND_EMAIL, side_effect=RuntimeError("smtp down"))
@patch(f"{REPO}.create_invite")
@patch(f"{REPO}.find_unaccepted_invite_by_email", return_value=None)
@patch(f"{REPO}.find_user_by_email", return_value=None)
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_create_invite_email_failure_swallowed(
    mock_get_family, mock_get_member, mock_find_user, mock_find_dup, mock_create, mock_send, db
):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    invite = _make_invite(token="t")
    mock_create.return_value = invite
    actor = _make_user(id=10)

    result = service.create_invite(
        db, family_id=1, actor=actor, email="new@test.com", role="member", simple_mode=False
    )

    assert result is invite  # email failure did not propagate


# ---------------------------------------------------------------------------
# list_invites
# ---------------------------------------------------------------------------


@patch(f"{REPO}.list_pending_invites")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_list_invites_returns_pending(mock_get_family, mock_get_member, mock_list, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    invites = [_make_invite(id=2), _make_invite(id=1)]
    mock_list.return_value = invites
    actor = _make_user(id=10)

    result = service.list_invites(db, family_id=1, actor=actor)

    assert result is invites
    mock_list.assert_called_once_with(db, 1)


@patch(f"{REPO}.list_pending_invites")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_list_invites_not_organizer(mock_get_family, mock_get_member, mock_list, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="member", user_id=10)
    actor = _make_user(id=10)

    with pytest.raises(ForbiddenError):
        service.list_invites(db, family_id=1, actor=actor)

    mock_list.assert_not_called()


# ---------------------------------------------------------------------------
# revoke_invite
# ---------------------------------------------------------------------------


@patch(f"{REPO}.delete_invite")
@patch(f"{REPO}.get_invite")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_revoke_invite_pending(mock_get_family, mock_get_member, mock_get_invite, mock_delete, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    invite = _make_invite(id=5, family_id=1, accepted_at=None)
    mock_get_invite.return_value = invite
    actor = _make_user(id=10)

    service.revoke_invite(db, family_id=1, invite_id=5, actor=actor)

    mock_delete.assert_called_once_with(db, invite)


@patch(f"{REPO}.delete_invite")
@patch(f"{REPO}.get_invite")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_revoke_invite_accepted(mock_get_family, mock_get_member, mock_get_invite, mock_delete, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    mock_get_invite.return_value = _make_invite(
        id=5, family_id=1, accepted_at=datetime.now(timezone.utc)
    )
    actor = _make_user(id=10)

    with pytest.raises(ConflictError):
        service.revoke_invite(db, family_id=1, invite_id=5, actor=actor)

    mock_delete.assert_not_called()


@patch(f"{REPO}.get_invite", return_value=None)
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_revoke_invite_not_found(mock_get_family, mock_get_member, mock_get_invite, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    actor = _make_user(id=10)

    with pytest.raises(NotFoundError):
        service.revoke_invite(db, family_id=1, invite_id=999, actor=actor)


@patch(f"{REPO}.get_invite")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_revoke_invite_wrong_family(mock_get_family, mock_get_member, mock_get_invite, db):
    mock_get_family.return_value = _make_family(id=1)
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    mock_get_invite.return_value = _make_invite(id=5, family_id=2)  # belongs to another family
    actor = _make_user(id=10)

    with pytest.raises(NotFoundError):
        service.revoke_invite(db, family_id=1, invite_id=5, actor=actor)


@patch(f"{REPO}.delete_invite")
@patch(f"{REPO}.get_invite")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{FAMILIES_REPO}.get_family")
def test_revoke_invite_declined(mock_get_family, mock_get_member, mock_get_invite, mock_delete, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="organizer", user_id=10)
    mock_get_invite.return_value = _make_invite(
        id=5, family_id=1, declined_at=datetime.now(timezone.utc)
    )
    actor = _make_user(id=10)

    with pytest.raises(ConflictError):
        service.revoke_invite(db, family_id=1, invite_id=5, actor=actor)

    mock_delete.assert_not_called()


# ---------------------------------------------------------------------------
# decline_invite
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_invite_by_token")
def test_decline_invite_sets_declined_at(mock_get, db):
    invite = _make_invite(token="tok", email="bob@test.com")
    mock_get.return_value = invite
    actor = _make_user(id=20, email="bob@test.com")

    service.decline_invite(db, token="tok", actor=actor)

    assert invite.declined_at is not None
    db.flush.assert_called_once()


@patch(f"{REPO}.get_invite_by_token", return_value=None)
def test_decline_invite_not_found(mock_get, db):
    actor = _make_user(id=20, email="bob@test.com")
    with pytest.raises(NotFoundError):
        service.decline_invite(db, token="missing", actor=actor)


@patch(f"{REPO}.get_invite_by_token")
def test_decline_invite_wrong_recipient(mock_get, db):
    mock_get.return_value = _make_invite(email="someone-else@test.com")
    actor = _make_user(id=20, email="bob@test.com")
    with pytest.raises(ForbiddenError):
        service.decline_invite(db, token="tok", actor=actor)


@patch(f"{REPO}.get_invite_by_token")
def test_decline_invite_already_accepted(mock_get, db):
    mock_get.return_value = _make_invite(
        email="bob@test.com", accepted_at=datetime.now(timezone.utc)
    )
    actor = _make_user(id=20, email="bob@test.com")
    with pytest.raises(ConflictError):
        service.decline_invite(db, token="tok", actor=actor)


@patch(f"{REPO}.get_invite_by_token")
def test_decline_invite_expired(mock_get, db):
    mock_get.return_value = _make_invite(email="bob@test.com", expires_in_days=-1)
    actor = _make_user(id=20, email="bob@test.com")
    with pytest.raises(ConflictError):
        service.decline_invite(db, token="tok", actor=actor)


# ---------------------------------------------------------------------------
# accept_invite
# ---------------------------------------------------------------------------


@patch(f"{FAMILIES_REPO}.get_family")
@patch(f"{FAMILIES_REPO}.create_family_member")
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=None)
@patch(f"{REPO}.get_invite_by_token")
def test_accept_invite_creates_membership(
    mock_get, mock_get_member, mock_create_member, mock_get_family, db
):
    invite = _make_invite(family_id=1, email="bob@test.com", role="organizer")
    mock_get.return_value = invite
    mock_get_family.return_value = _make_family(id=1, name="Smith Family")
    actor = _make_user(id=20, email="bob@test.com")

    result = service.accept_invite(db, token="tok", actor=actor)

    mock_create_member.assert_called_once_with(
        db, family_id=1, user_id=20, role="organizer"
    )
    assert invite.accepted_at is not None
    assert result == {"family": {"id": 1, "name": "Smith Family"}, "role": "organizer"}


@patch(f"{FAMILIES_REPO}.create_family_member")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{REPO}.get_invite_by_token")
def test_accept_invite_already_member(mock_get, mock_get_member, mock_create_member, db):
    mock_get.return_value = _make_invite(family_id=1, email="bob@test.com")
    mock_get_member.return_value = _make_member(role="member", user_id=20)
    actor = _make_user(id=20, email="bob@test.com")

    with pytest.raises(ConflictError):
        service.accept_invite(db, token="tok", actor=actor)

    mock_create_member.assert_not_called()


@patch(f"{REPO}.get_invite_by_token", return_value=None)
def test_accept_invite_not_found(mock_get, db):
    actor = _make_user(id=20, email="bob@test.com")
    with pytest.raises(NotFoundError):
        service.accept_invite(db, token="missing", actor=actor)


@patch(f"{REPO}.get_invite_by_token")
def test_accept_invite_wrong_recipient(mock_get, db):
    mock_get.return_value = _make_invite(email="someone-else@test.com")
    actor = _make_user(id=20, email="bob@test.com")
    with pytest.raises(ForbiddenError):
        service.accept_invite(db, token="tok", actor=actor)


@patch(f"{REPO}.get_invite_by_token")
def test_accept_invite_declined(mock_get, db):
    mock_get.return_value = _make_invite(
        email="bob@test.com", declined_at=datetime.now(timezone.utc)
    )
    actor = _make_user(id=20, email="bob@test.com")
    with pytest.raises(ConflictError):
        service.accept_invite(db, token="tok", actor=actor)


@patch(f"{REPO}.get_invite_by_token")
def test_accept_invite_expired(mock_get, db):
    mock_get.return_value = _make_invite(email="bob@test.com", expires_in_days=-1)
    actor = _make_user(id=20, email="bob@test.com")
    with pytest.raises(ConflictError):
        service.accept_invite(db, token="tok", actor=actor)


# ---------------------------------------------------------------------------
# list_incoming_invites
# ---------------------------------------------------------------------------


@patch(f"{REPO}.list_incoming_invites")
def test_list_incoming_invites_maps_rows(mock_list, db):
    invite = _make_invite(id=7, token="tok-7", email="bob@test.com", role="member")
    family = _make_family(id=3, name="Boone Family")
    inviter = _make_user(id=2, name="Alice")
    mock_list.return_value = [(invite, family, inviter)]
    actor = _make_user(id=20, email="bob@test.com")

    result = service.list_incoming_invites(db, actor=actor)

    mock_list.assert_called_once_with(db, "bob@test.com")
    assert result == [
        {
            "id": 7,
            "token": "tok-7",
            "role": "member",
            "expires_at": invite.expires_at,
            "created_at": invite.created_at,
            "family": {"id": 3, "name": "Boone Family"},
            "invited_by": {"id": 2, "name": "Alice"},
        }
    ]


@patch(f"{REPO}.list_incoming_invites")
def test_list_incoming_invites_filters_expired(mock_list, db):
    expired = _make_invite(id=8, token="old", email="bob@test.com", expires_in_days=-1)
    family = _make_family(id=3, name="Boone Family")
    inviter = _make_user(id=2, name="Alice")
    mock_list.return_value = [(expired, family, inviter)]
    actor = _make_user(id=20, email="bob@test.com")

    result = service.list_incoming_invites(db, actor=actor)

    assert result == []
