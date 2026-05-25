from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.collection_item import CollectionItem
from app.models.gift import Gift
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
    ).order_by(GiftList.updated_at.desc())
    return list(db.execute(query).scalars().all())


def get_shared_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    shared_list_ids = select(ListShare.list_id).where(ListShare.user_id == user_id)
    query = select(GiftList).where(
        GiftList.id.in_(shared_list_ids),
        GiftList.is_archived == archived,
    ).order_by(GiftList.updated_at.desc())
    return list(db.execute(query).scalars().all())


def get_all_visible_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    shared_list_ids = select(ListShare.list_id).where(ListShare.user_id == user_id)
    query = select(GiftList).where(
        or_(
            GiftList.owner_id == user_id,
            GiftList.id.in_(shared_list_ids),
        ),
        GiftList.is_archived == archived,
    ).order_by(GiftList.updated_at.desc())
    return list(db.execute(query).scalars().all())


def get_list_by_id(db: Session, list_id: int) -> GiftList | None:
    return db.get(GiftList, list_id)


def update_list(db: Session, gift_list: GiftList, updates: dict) -> GiftList:
    for field, value in updates.items():
        setattr(gift_list, field, value)
    db.flush()
    return gift_list


def delete_list(db: Session, gift_list: GiftList) -> None:
    list_id = gift_list.id
    db.execute(delete(CollectionItem).where(CollectionItem.list_id == list_id))
    db.execute(delete(ListShare).where(ListShare.list_id == list_id))
    db.execute(delete(Gift).where(Gift.list_id == list_id))
    db.delete(gift_list)
    db.flush()


def get_unseen_share_count(db: Session, user_id: int) -> int:
    from sqlalchemy import func as sa_func
    result = db.execute(
        select(sa_func.count())
        .select_from(ListShare)
        .where(ListShare.user_id == user_id, ListShare.seen_at.is_(None))
    ).scalar()
    return result or 0


def get_lists_shared_by_user(
    db: Session, owner_id: int, shared_with_user_id: int
) -> list[GiftList]:
    shared_list_ids = select(ListShare.list_id).where(
        ListShare.user_id == shared_with_user_id
    )
    query = (
        select(GiftList)
        .where(
            GiftList.owner_id == owner_id,
            GiftList.id.in_(shared_list_ids),
            GiftList.is_archived == False,
        )
        .order_by(GiftList.updated_at.desc())
    )
    return list(db.execute(query).scalars().all())


def mark_share_seen(db: Session, list_id: int, user_id: int) -> None:
    from datetime import datetime, timezone
    share = db.execute(
        select(ListShare).where(
            ListShare.list_id == list_id,
            ListShare.user_id == user_id,
            ListShare.seen_at.is_(None),
        )
    ).scalar_one_or_none()
    if share:
        share.seen_at = datetime.now(timezone.utc)
        db.flush()
