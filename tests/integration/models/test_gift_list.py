from app.models.gift_list import GiftList
from app.models.user import User


def test_create_gift_list(db):
    owner = User(email="owner@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(
        name="Christmas 2026",
        description="My holiday wishlist",
        owner_id=owner.id,
    )
    db.add(gift_list)
    db.flush()

    assert gift_list.id is not None
    assert gift_list.name == "Christmas 2026"
    assert gift_list.description == "My holiday wishlist"
    assert gift_list.owner_id == owner.id
    assert gift_list.created_at is not None
    assert gift_list.updated_at is not None


def test_create_gift_list_no_description(db):
    owner = User(email="owner2@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(name="Birthday", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    assert gift_list.id is not None
    assert gift_list.description is None
