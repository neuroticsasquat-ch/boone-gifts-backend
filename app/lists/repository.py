from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.gift_list import GiftList
from app.models.list_share import ListShare


def create_list(
    db: Session, name: str, description: str | None, owner_id: int
) -> GiftList:
    gift_list = GiftList(name=name, description=description, owner_id=owner_id)
    db.add(gift_list)
    db.flush()
    return gift_list


def get_lists_by_owner(db: Session, owner_id: int, archived: bool = False) -> list[GiftList]:
    query = select(GiftList).where(
        GiftList.owner_id == owner_id,
        GiftList.is_archived == archived,
    )
    return list(db.execute(query).scalars().all())


def get_shared_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    shared_list_ids = select(ListShare.list_id).where(ListShare.user_id == user_id)
    query = select(GiftList).where(
        GiftList.id.in_(shared_list_ids),
        GiftList.is_archived == archived,
    )
    return list(db.execute(query).scalars().all())


def get_all_visible_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    shared_list_ids = select(ListShare.list_id).where(ListShare.user_id == user_id)
    query = select(GiftList).where(
        or_(
            GiftList.owner_id == user_id,
            GiftList.id.in_(shared_list_ids),
        ),
        GiftList.is_archived == archived,
    )
    return list(db.execute(query).scalars().all())


def get_list_by_id(db: Session, list_id: int) -> GiftList | None:
    return db.get(GiftList, list_id)


def update_list(db: Session, gift_list: GiftList, updates: dict) -> GiftList:
    for field, value in updates.items():
        setattr(gift_list, field, value)
    db.flush()
    return gift_list


def delete_list(db: Session, gift_list: GiftList) -> None:
    db.delete(gift_list)
    db.flush()
