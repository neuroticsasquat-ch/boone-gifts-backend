from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.account_person import AccountPerson
from app.models.gift_list import GiftList


def get_people(db: Session, user_id: int) -> list[AccountPerson]:
    """The account's people in display order. `position` ties are broken by id
    so the order never flickers between requests."""
    query = (
        select(AccountPerson)
        .where(AccountPerson.user_id == user_id)
        .order_by(AccountPerson.position, AccountPerson.id)
    )
    return list(db.execute(query).scalars().all())


def get_person(db: Session, user_id: int, person_id: int) -> AccountPerson | None:
    """A person, but only if this account owns them. Scoping the lookup rather
    than loading by id and comparing afterwards is what keeps another account's
    id indistinguishable from one that does not exist."""
    query = select(AccountPerson).where(
        AccountPerson.id == person_id,
        AccountPerson.user_id == user_id,
    )
    return db.execute(query).scalar_one_or_none()


def count_lists_labelled(db: Session, owner_id: int) -> int:
    """How many of this account's lists carry any label at all."""
    result = db.execute(
        select(func.count())
        .select_from(GiftList)
        .where(
            GiftList.owner_id == owner_id,
            GiftList.account_person_id.isnot(None),
        )
    ).scalar()
    return result or 0


def count_lists_for_people(db: Session, owner_id: int, person_ids: list[int]) -> int:
    if not person_ids:
        return 0
    result = db.execute(
        select(func.count())
        .select_from(GiftList)
        .where(
            GiftList.owner_id == owner_id,
            GiftList.account_person_id.in_(person_ids),
        )
    ).scalar()
    return result or 0


def clear_labels(db: Session, owner_id: int, person_ids: list[int] | None = None) -> None:
    """Null `account_person_id` on this account's lists — all of them, or only
    those pointing at `person_ids`. The lists, their gifts, their shares and
    their claims are untouched: §4.4 nulls, it never cascades.

    This must run *before* the people rows are deleted; the FK is enforced.
    """
    if person_ids is not None and not person_ids:
        return
    statement = update(GiftList).where(GiftList.owner_id == owner_id)
    if person_ids is None:
        statement = statement.where(GiftList.account_person_id.isnot(None))
    else:
        statement = statement.where(GiftList.account_person_id.in_(person_ids))
    db.execute(statement.values(account_person_id=None))
    db.flush()


def delete_people(db: Session, people: list[AccountPerson]) -> None:
    for person in people:
        db.delete(person)
    db.flush()


def create_person(db: Session, user_id: int, name: str, position: int) -> AccountPerson:
    person = AccountPerson(user_id=user_id, name=name, position=position)
    db.add(person)
    db.flush()
    return person
