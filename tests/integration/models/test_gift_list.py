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


def test_gift_list_defaults_have_no_recipient(db):
    owner = User(email="owner-nr@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(name="Mine", owner_id=owner.id)
    db.add(gift_list)
    db.flush()

    assert gift_list.recipient_name is None
    assert gift_list.recipient_has_account is None
    assert gift_list.kept_for_absent_person is False


def test_kept_for_absent_person_false_when_recipient_has_account(db):
    owner = User(email="owner-ha@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(
        name="Jane's list",
        owner_id=owner.id,
        recipient_name="Jane",
        recipient_has_account=True,
    )
    db.add(gift_list)
    db.flush()

    assert gift_list.kept_for_absent_person is False


def test_kept_for_absent_person_true_only_for_named_absent_recipient(db):
    owner = User(email="owner-abs@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(
        name="Beth's list",
        owner_id=owner.id,
        recipient_name="Beth",
        recipient_has_account=False,
    )
    db.add(gift_list)
    db.flush()

    assert gift_list.kept_for_absent_person is True
