import pytest
from sqlalchemy.exc import IntegrityError

from app.models.account_person import AccountPerson
from app.models.gift_list import GiftList


def _people(db, user, *names):
    people = [
        AccountPerson(user_id=user.id, name=name, position=index)
        for index, name in enumerate(names)
    ]
    db.add_all(people)
    db.flush()
    return people


def test_account_person_defaults(db, member_user):
    gran, = _people(db, member_user, "Gran")
    assert gran.id is not None
    assert gran.position == 0
    assert gran.created_at is not None


def test_user_is_not_a_shared_account_by_default(db, member_user):
    assert member_user.is_shared_account is False


def test_names_are_unique_within_an_account(db, member_user):
    _people(db, member_user, "Gran")
    db.add(AccountPerson(user_id=member_user.id, name="Gran", position=1))
    with pytest.raises(IntegrityError):
        db.flush()


def test_two_accounts_may_share_a_name(db, member_user, admin_user):
    _people(db, member_user, "Gran")
    _people(db, admin_user, "Gran")
    # No error: the constraint is on (user_id, name), not on name.


def test_list_label_is_nullable(db, member_user):
    gift_list = GiftList(name="Household", owner_id=member_user.id)
    db.add(gift_list)
    db.flush()
    assert gift_list.account_person_id is None
    assert gift_list.account_person_name is None


def test_list_exposes_the_person_name(db, member_user):
    gran, = _people(db, member_user, "Gran")
    gift_list = GiftList(
        name="Gran's List", owner_id=member_user.id, account_person_id=gran.id
    )
    db.add(gift_list)
    db.flush()
    assert gift_list.account_person_name == "Gran"


def test_deleting_a_referenced_person_is_refused_by_the_database(db, member_user):
    # PRAGMA foreign_keys=ON is live on every connection, so the label has to be
    # nulled before the person goes (§4.4). This is what enforces that order.
    gran, = _people(db, member_user, "Gran")
    db.add(GiftList(name="Gran's List", owner_id=member_user.id,
                    account_person_id=gran.id))
    db.flush()

    db.delete(gran)
    with pytest.raises(IntegrityError):
        db.flush()
