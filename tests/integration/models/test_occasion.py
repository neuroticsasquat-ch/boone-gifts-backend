import sqlalchemy

import pytest

from app.models.occasion import Occasion
from app.models.occasion_item import OccasionItem
from app.models.gift_list import GiftList
from app.models.user import User


def test_create_occasion(db):
    user = User(email="collector@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    occasion = Occasion(name="Christmas 2026", owner_id=user.id)
    db.add(occasion)
    db.flush()

    assert occasion.id is not None
    assert occasion.name == "Christmas 2026"
    assert occasion.owner_id == user.id
    assert occasion.description is None
    assert occasion.created_at is not None
    assert occasion.updated_at is not None


def test_create_occasion_no_description(db):
    user = User(email="collector2@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    occasion = Occasion(
        name="Birthday Ideas",
        description="Gift ideas for birthdays",
        owner_id=user.id,
    )
    db.add(occasion)
    db.flush()

    assert occasion.description == "Gift ideas for birthdays"


def test_create_occasion_item(db):
    user = User(email="collector3@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    occasion = Occasion(name="My Occasion", owner_id=user.id)
    db.add(occasion)
    db.flush()

    gift_list = GiftList(name="Wishlist", owner_id=user.id)
    db.add(gift_list)
    db.flush()

    item = OccasionItem(occasion_id=occasion.id, list_id=gift_list.id)
    db.add(item)
    db.flush()

    assert item.id is not None
    assert item.occasion_id == occasion.id
    assert item.list_id == gift_list.id
    assert item.created_at is not None


def test_occasion_item_unique_constraint(db):
    user = User(email="collector4@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    occasion = Occasion(name="Dupes", owner_id=user.id)
    db.add(occasion)
    db.flush()

    gift_list = GiftList(name="Wishlist", owner_id=user.id)
    db.add(gift_list)
    db.flush()

    item1 = OccasionItem(occasion_id=occasion.id, list_id=gift_list.id)
    db.add(item1)
    db.flush()

    item2 = OccasionItem(occasion_id=occasion.id, list_id=gift_list.id)
    db.add(item2)

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()
