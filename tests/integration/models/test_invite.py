from datetime import datetime, timedelta, timezone

from app.models.invite import Invite
from app.models.user import User


def test_create_invite(db):
    admin = User(email="admin@test.com", name="Admin", password_hash="h", role="admin")
    db.add(admin)
    db.flush()

    invite = Invite(
        email="new@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin.id,
    )
    db.add(invite)
    db.flush()

    assert invite.id is not None
    assert invite.token is not None
    assert len(invite.token) == 36  # UUID4 format
    assert invite.used_at is None
    assert invite.created_at is not None


def test_invite_is_valid(db):
    admin = User(email="admin2@test.com", name="Admin", password_hash="h", role="admin")
    db.add(admin)
    db.flush()

    invite = Invite(
        email="valid@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin.id,
    )
    db.add(invite)
    db.flush()

    assert invite.is_valid is True


def test_invite_expired(db):
    admin = User(email="admin3@test.com", name="Admin", password_hash="h", role="admin")
    db.add(admin)
    db.flush()

    invite = Invite(
        email="expired@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        invited_by_id=admin.id,
    )
    db.add(invite)
    db.flush()

    assert invite.is_valid is False


def test_invite_used(db):
    admin = User(email="admin4@test.com", name="Admin", password_hash="h", role="admin")
    db.add(admin)
    db.flush()

    invite = Invite(
        email="used@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin.id,
    )
    invite.used_at = datetime.now(timezone.utc)
    db.add(invite)
    db.flush()

    assert invite.is_valid is False
