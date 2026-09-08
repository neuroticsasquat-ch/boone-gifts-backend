import sqlalchemy

import pytest

from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.gift_list import GiftList
from app.models.user import User


def test_create_folder(db):
    user = User(email="collector@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    folder = Folder(name="Christmas 2026", owner_id=user.id)
    db.add(folder)
    db.flush()

    assert folder.id is not None
    assert folder.name == "Christmas 2026"
    assert folder.owner_id == user.id
    assert folder.description is None
    assert folder.created_at is not None
    assert folder.updated_at is not None


def test_create_folder_no_description(db):
    user = User(email="collector2@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    folder = Folder(
        name="Birthday Ideas",
        description="Gift ideas for birthdays",
        owner_id=user.id,
    )
    db.add(folder)
    db.flush()

    assert folder.description == "Gift ideas for birthdays"


def test_create_folder_item(db):
    user = User(email="collector3@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    folder = Folder(name="My Folder", owner_id=user.id)
    db.add(folder)
    db.flush()

    gift_list = GiftList(name="Wishlist", owner_id=user.id)
    db.add(gift_list)
    db.flush()

    item = FolderItem(folder_id=folder.id, list_id=gift_list.id)
    db.add(item)
    db.flush()

    assert item.id is not None
    assert item.folder_id == folder.id
    assert item.list_id == gift_list.id
    assert item.created_at is not None


def test_folder_item_unique_constraint(db):
    user = User(email="collector4@test.com", name="Collector", password_hash="h")
    db.add(user)
    db.flush()

    folder = Folder(name="Dupes", owner_id=user.id)
    db.add(folder)
    db.flush()

    gift_list = GiftList(name="Wishlist", owner_id=user.id)
    db.add(gift_list)
    db.flush()

    item1 = FolderItem(folder_id=folder.id, list_id=gift_list.id)
    db.add(item1)
    db.flush()

    item2 = FolderItem(folder_id=folder.id, list_id=gift_list.id)
    db.add(item2)

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()
