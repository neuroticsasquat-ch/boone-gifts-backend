import pytest
import sqlalchemy

from app.models.family import Family
from app.models.occasion import Occasion
from app.models.user import User


def _user(db, email: str) -> User:
    user = User(email=email, name="Occasion Tester", password_hash="h")
    db.add(user)
    db.flush()
    return user


def _family(db, creator: User) -> Family:
    family = Family(name="The Boones", created_by_id=creator.id)
    db.add(family)
    db.flush()
    return family


def test_create_occasion(db):
    user = _user(db, "occasion_model1@test.com")
    family = _family(db, user)

    occasion = Occasion(
        family_id=family.id, name="Christmas 2026", created_by_id=user.id
    )
    db.add(occasion)
    db.flush()

    assert occasion.id is not None
    assert occasion.family_id == family.id
    assert occasion.name == "Christmas 2026"
    assert occasion.created_by_id == user.id
    assert occasion.created_at is not None
    assert occasion.updated_at is not None


def test_occasion_defaults_to_active(db):
    user = _user(db, "occasion_model2@test.com")
    family = _family(db, user)

    occasion = Occasion(family_id=family.id, name="Gran's 80th", created_by_id=user.id)
    db.add(occasion)
    db.flush()

    assert occasion.is_archived is False


def test_occasion_requires_an_existing_family(db):
    user = _user(db, "occasion_model3@test.com")

    db.add(Occasion(family_id=99999, name="Orphan", created_by_id=user.id))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()


def test_a_family_may_hold_several_occasions(db):
    user = _user(db, "occasion_model4@test.com")
    family = _family(db, user)

    for name in ("Christmas 2026", "Gran's 80th"):
        db.add(Occasion(family_id=family.id, name=name, created_by_id=user.id))
    db.flush()

    rows = (
        db.execute(
            sqlalchemy.select(Occasion).where(Occasion.family_id == family.id)
        )
        .scalars()
        .all()
    )
    assert {row.name for row in rows} == {"Christmas 2026", "Gran's 80th"}
