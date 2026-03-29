from decimal import Decimal

from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.user import User


def test_create_gift(db):
    """Test creating a gift with all fields populated."""
    owner = User(email="owner@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(name="Birthday", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    gift = Gift(
        list_id=gift_list.id,
        name="Book",
        description="A good book",
        url="https://example.com/book",
        price=Decimal("19.99"),
    )
    db.add(gift)
    db.flush()

    assert gift.id is not None
    assert gift.list_id == gift_list.id
    assert gift.name == "Book"
    assert gift.description == "A good book"
    assert gift.url == "https://example.com/book"
    assert gift.price == Decimal("19.99")
    assert gift.claimed_by_id is None
    assert gift.claimed_at is None
    assert gift.created_at is not None
    assert gift.updated_at is not None


def test_create_gift_minimal(db):
    """Test creating a gift with only required fields."""
    owner = User(email="owner2@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(name="Minimal", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    gift = Gift(list_id=gift_list.id, name="Surprise")
    db.add(gift)
    db.flush()

    assert gift.id is not None
    assert gift.description is None
    assert gift.url is None
    assert gift.price is None


def test_claim_gift(db):
    """Test claiming a gift by setting claimed_by_id."""
    owner = User(email="owner3@test.com", name="Owner", password_hash="h")
    claimer = User(email="claimer@test.com", name="Claimer", password_hash="h")
    db.add_all([owner, claimer])
    db.flush()

    gift_list = GiftList(name="Claims", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    gift = Gift(list_id=gift_list.id, name="Gadget")
    db.add(gift)
    db.flush()

    assert gift.claimed_by_id is None

    gift.claimed_by_id = claimer.id
    db.flush()

    assert gift.claimed_by_id == claimer.id
