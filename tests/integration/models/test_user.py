import pytest

from app.models.user import User


def test_create_user(db):
    user = User(
        email="test@example.com",
        name="Test User",
        password_hash="hashed",
        role="admin",
    )
    db.add(user)
    db.flush()

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.name == "Test User"
    assert user.role == "admin"
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None


def test_user_default_role(db):
    user = User(
        email="member@example.com",
        name="Member",
        password_hash="hashed",
    )
    db.add(user)
    db.flush()

    assert user.role == "member"


def test_user_email_unique(db):
    import sqlalchemy

    user1 = User(email="dupe@example.com", name="First", password_hash="h")
    db.add(user1)
    db.flush()

    user2 = User(email="dupe@example.com", name="Second", password_hash="h")
    db.add(user2)

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()


def test_user_password_hashing():
    user = User(email="a@b.com", name="A", password_hash="x")
    user.set_password("secret123")
    assert user.password_hash != "secret123"
    assert user.check_password("secret123") is True
    assert user.check_password("wrong") is False
