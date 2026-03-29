import sqlalchemy

import pytest

from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.models.user import User


def test_create_list_share(db):
    owner = User(email="owner@test.com", name="Owner", password_hash="h")
    viewer = User(email="viewer@test.com", name="Viewer", password_hash="h")
    db.add_all([owner, viewer])
    db.flush()

    gift_list = GiftList(name="Shared List", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    share = ListShare(list_id=gift_list.id, user_id=viewer.id)
    db.add(share)
    db.flush()

    assert share.id is not None
    assert share.list_id == gift_list.id
    assert share.user_id == viewer.id
    assert share.created_at is not None


def test_list_share_unique_constraint(db):
    owner = User(email="owner2@test.com", name="Owner", password_hash="h")
    viewer = User(email="viewer2@test.com", name="Viewer", password_hash="h")
    db.add_all([owner, viewer])
    db.flush()

    gift_list = GiftList(name="Dupe Test", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    share1 = ListShare(list_id=gift_list.id, user_id=viewer.id)
    db.add(share1)
    db.flush()

    share2 = ListShare(list_id=gift_list.id, user_id=viewer.id)
    db.add(share2)

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()
