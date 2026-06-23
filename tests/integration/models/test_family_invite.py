from datetime import datetime, timezone

import sqlalchemy
import pytest

from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.user import User


def test_create_family_invite(db):
    user = User(email="finv_test1@test.com", name="User One", password_hash="h")
    db.add(user)
    db.flush()

    family = Family(name="The Boones", created_by_id=user.id)
    db.add(family)
    db.flush()

    invite = FamilyInvite(
        family_id=family.id,
        email="invitee@test.com",
        role="member",
        token="aaaabbbb-cccc-dddd-eeee-ffffgggghhhh",
        invited_by_id=user.id,
        expires_at=datetime(2030, 1, 1),
    )
    db.add(invite)
    db.flush()

    assert invite.id is not None
    assert invite.family_id == family.id
    assert invite.email == "invitee@test.com"
    assert invite.role == "member"
    assert invite.token == "aaaabbbb-cccc-dddd-eeee-ffffgggghhhh"
    assert invite.invited_by_id == user.id
    assert invite.expires_at == datetime(2030, 1, 1)
    assert invite.accepted_at is None
    assert invite.created_at is not None


def test_family_invite_token_unique_constraint(db):
    user = User(email="finv_test2a@test.com", name="User Two", password_hash="h")
    db.add(user)
    db.flush()

    family = Family(name="Test Family", created_by_id=user.id)
    db.add(family)
    db.flush()

    invite1 = FamilyInvite(
        family_id=family.id,
        email="invitee1@test.com",
        role="member",
        token="token-unique-1234567890123456",
        invited_by_id=user.id,
        expires_at=datetime(2030, 1, 1),
    )
    db.add(invite1)
    db.flush()

    invite2 = FamilyInvite(
        family_id=family.id,
        email="invitee2@test.com",
        role="member",
        token="token-unique-1234567890123456",
        invited_by_id=user.id,
        expires_at=datetime(2030, 1, 1),
    )
    db.add(invite2)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()


def test_family_invite_accepted_at_nullable(db):
    user = User(email="finv_test3@test.com", name="User Three", password_hash="h")
    db.add(user)
    db.flush()

    family = Family(name="Nullable Test Family", created_by_id=user.id)
    db.add(family)
    db.flush()

    invite = FamilyInvite(
        family_id=family.id,
        email="invitee@test.com",
        role="member",
        token="bbbbcccc-dddd-eeee-ffff-gggghhhh1111",
        invited_by_id=user.id,
        expires_at=datetime(2030, 1, 1),
        accepted_at=None,
    )
    db.add(invite)
    db.flush()

    assert invite.accepted_at is None
