from app.models.account_person import AccountPerson
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
    assert gift_list.kept_for_absent_person is False


def test_kept_for_absent_person_true_for_any_named_recipient(db):
    # Since NEU-1230 a recipient has one meaning, so the name alone decides it.
    owner = User(email="owner-abs@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()

    gift_list = GiftList(
        name="Beth's list",
        owner_id=owner.id,
        recipient_name="Beth",
    )
    db.add(gift_list)
    db.flush()

    assert gift_list.kept_for_absent_person is True


def test_kept_for_absent_person_false_for_an_account_person_list(db):
    owner = User(email="owner-ap@test.com", name="Owner", password_hash="h")
    db.add(owner)
    db.flush()
    person = AccountPerson(user_id=owner.id, name="Gran", position=0)
    db.add(person)
    db.flush()

    gift_list = GiftList(
        name="Gran's list",
        owner_id=owner.id,
        account_person_id=person.id,
    )
    db.add(gift_list)
    db.flush()

    assert gift_list.kept_for_absent_person is False
