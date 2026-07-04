from datetime import datetime, timedelta, timezone

from app.schemas.family_invite import (
    FamilyInviteRead,
    FamilyInviteStatus,
    IncomingFamilyInviteRead,
)


def _base_read_kwargs(**overrides):
    kwargs = dict(
        id=1,
        family_id=1,
        email="bob@test.com",
        role="member",
        simple_mode=False,
        token="tok-1",
        invited_by_id=2,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        accepted_at=None,
        declined_at=None,
        created_at=datetime.now(timezone.utc),
    )
    kwargs.update(overrides)
    return kwargs


def test_status_declined_when_declined_at_set():
    read = FamilyInviteRead(**_base_read_kwargs(declined_at=datetime.now(timezone.utc)))
    assert read.status == FamilyInviteStatus.declined


def test_status_accepted_takes_precedence_over_declined():
    read = FamilyInviteRead(
        **_base_read_kwargs(
            accepted_at=datetime.now(timezone.utc),
            declined_at=datetime.now(timezone.utc),
        )
    )
    assert read.status == FamilyInviteStatus.accepted


def test_status_pending_when_nothing_set():
    read = FamilyInviteRead(**_base_read_kwargs())
    assert read.status == FamilyInviteStatus.pending


def test_incoming_family_invite_read_nested_shape():
    read = IncomingFamilyInviteRead(
        id=5,
        token="tok-5",
        role="member",
        family={"id": 9, "name": "Boone Family"},
        invited_by={"id": 2, "name": "Alice"},
        expires_at=datetime.now(timezone.utc) + timedelta(days=3),
        created_at=datetime.now(timezone.utc),
    )
    assert read.family.name == "Boone Family"
    assert read.invited_by.name == "Alice"
    assert read.role == "member"
