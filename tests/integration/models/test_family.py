import sqlalchemy
import pytest

from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.user import User


def test_create_family(db):
    user = User(email="family_test1@test.com", name="User One", password_hash="h")
    db.add(user)
    db.flush()

    family = Family(name="The Boones", created_by_id=user.id)
    db.add(family)
    db.flush()

    assert family.id is not None
    assert family.name == "The Boones"
    assert family.created_by_id == user.id
    assert family.created_at is not None
    assert family.updated_at is not None


def test_create_family_member(db):
    user = User(email="family_test2@test.com", name="User Two", password_hash="h")
    db.add(user)
    db.flush()

    family = Family(name="Test Family", created_by_id=user.id)
    db.add(family)
    db.flush()

    member = FamilyMember(family_id=family.id, user_id=user.id, role="organizer")
    db.add(member)
    db.flush()

    assert member.id is not None
    assert member.family_id == family.id
    assert member.user_id == user.id
    assert member.role == "organizer"
    assert member.joined_at is not None
    assert member.created_at is not None


def test_family_member_unique_constraint(db):
    user_a = User(email="family_test3a@test.com", name="User 3A", password_hash="h")
    user_b = User(email="family_test3b@test.com", name="User 3B", password_hash="h")
    db.add_all([user_a, user_b])
    db.flush()

    family = Family(name="Constraint Family", created_by_id=user_a.id)
    db.add(family)
    db.flush()

    member1 = FamilyMember(family_id=family.id, user_id=user_b.id, role="member")
    db.add(member1)
    db.flush()

    member2 = FamilyMember(family_id=family.id, user_id=user_b.id, role="member")
    db.add(member2)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()


def test_family_member_role_values(db):
    user_a = User(email="family_test4a@test.com", name="User 4A", password_hash="h")
    user_b = User(email="family_test4b@test.com", name="User 4B", password_hash="h")
    db.add_all([user_a, user_b])
    db.flush()

    family = Family(name="Role Test Family", created_by_id=user_a.id)
    db.add(family)
    db.flush()

    organizer = FamilyMember(family_id=family.id, user_id=user_a.id, role="organizer")
    regular = FamilyMember(family_id=family.id, user_id=user_b.id, role="member")
    db.add_all([organizer, regular])
    db.flush()

    assert organizer.role == "organizer"
    assert regular.role == "member"


def test_user_simple_mode_default(db):
    user = User(email="family_test5@test.com", name="User Five", password_hash="h")
    db.add(user)
    db.flush()

    assert user.simple_mode == False
