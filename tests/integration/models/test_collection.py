import sqlalchemy

import pytest

from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.gift_list import GiftList
from app.models.user import User


def test_create_collection(db):
    user = User(email="collector@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    collection = Collection(name="Christmas 2026", owner_id=user.id)
    db.add(collection)
    db.flush()

    assert collection.id is not None
    assert collection.name == "Christmas 2026"
    assert collection.owner_id == user.id
    assert collection.description is None
    assert collection.created_at is not None
    assert collection.updated_at is not None


def test_create_collection_no_description(db):
    user = User(email="collector2@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    collection = Collection(
        name="Birthday Ideas",
        description="Gift ideas for birthdays",
        owner_id=user.id,
    )
    db.add(collection)
    db.flush()

    assert collection.description == "Gift ideas for birthdays"


def test_create_collection_item(db):
    user = User(email="collector3@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    collection = Collection(name="My Collection", owner_id=user.id)
    db.add(collection)
    db.flush()

    gift_list = GiftList(name="Wishlist", owner_id=user.id)
    db.add(gift_list)
    db.flush()

    item = CollectionItem(collection_id=collection.id, list_id=gift_list.id)
    db.add(item)
    db.flush()

    assert item.id is not None
    assert item.collection_id == collection.id
    assert item.list_id == gift_list.id
    assert item.created_at is not None


def test_collection_item_unique_constraint(db):
    user = User(email="collector4@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    collection = Collection(name="Dupes", owner_id=user.id)
    db.add(collection)
    db.flush()

    gift_list = GiftList(name="Wishlist", owner_id=user.id)
    db.add(gift_list)
    db.flush()

    item1 = CollectionItem(collection_id=collection.id, list_id=gift_list.id)
    db.add(item1)
    db.flush()

    item2 = CollectionItem(collection_id=collection.id, list_id=gift_list.id)
    db.add(item2)

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()
