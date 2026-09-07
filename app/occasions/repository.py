from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.occasion import Occasion
from app.models.occasion_item import OccasionItem
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_share import ListShare


def create_occasion(
    db: Session, name: str, description: str | None, owner_id: int
) -> Occasion:
    occasion = Occasion(name=name, description=description, owner_id=owner_id)
    db.add(occasion)
    db.flush()
    return occasion


def get_occasions_for_user(db: Session, owner_id: int, archived: bool = False) -> list[Occasion]:
    return list(
        db.execute(
            select(Occasion).where(
                Occasion.owner_id == owner_id,
                Occasion.is_archived == archived,
            )
        )
        .scalars()
        .all()
    )


def get_occasion_by_id(db: Session, occasion_id: int) -> Occasion | None:
    return db.get(Occasion, occasion_id)


def get_lists_for_occasion(db: Session, occasion: Occasion) -> list[GiftList]:
    list_ids = [item.list_id for item in occasion.items]
    if not list_ids:
        return []
    return list(
        db.execute(select(GiftList).where(GiftList.id.in_(list_ids))).scalars().all()
    )


def update_occasion(
    db: Session, occasion: Occasion, update_data: dict
) -> Occasion:
    for key, value in update_data.items():
        setattr(occasion, key, value)
    db.flush()
    return occasion


def delete_occasion(db: Session, occasion: Occasion) -> None:
    db.delete(occasion)
    db.flush()


def get_gift_list_by_id(db: Session, list_id: int) -> GiftList | None:
    return db.get(GiftList, list_id)


def find_share(db: Session, list_id: int, user_id: int) -> ListShare | None:
    return db.execute(
        select(ListShare).where(
            ListShare.list_id == list_id,
            ListShare.user_id == user_id,
        )
    ).scalar_one_or_none()


def find_occasion_item(
    db: Session, occasion_id: int, list_id: int
) -> OccasionItem | None:
    return db.execute(
        select(OccasionItem).where(
            OccasionItem.occasion_id == occasion_id,
            OccasionItem.list_id == list_id,
        )
    ).scalar_one_or_none()


def create_occasion_item(
    db: Session, occasion_id: int, list_id: int
) -> OccasionItem:
    item = OccasionItem(occasion_id=occasion_id, list_id=list_id)
    db.add(item)
    db.flush()
    return item


def delete_occasion_item(db: Session, item: OccasionItem) -> None:
    db.delete(item)
    db.flush()


def get_occasion_ids_for_list(db: Session, list_id: int, owner_id: int) -> list[int]:
    result = db.execute(
        select(OccasionItem.occasion_id)
        .join(Occasion, OccasionItem.occasion_id == Occasion.id)
        .where(
            OccasionItem.list_id == list_id,
            Occasion.owner_id == owner_id,
        )
    ).scalars().all()
    return list(result)


def get_shopping_list_items(
    db: Session, occasion_id: int, user_id: int
) -> list[dict]:
    """Return all gifts claimed by user_id within the given occasion."""
    rows = db.execute(
        select(Gift, GiftList.name.label("list_name"))
        .join(GiftList, Gift.list_id == GiftList.id)
        .join(OccasionItem, OccasionItem.list_id == GiftList.id)
        .where(
            OccasionItem.occasion_id == occasion_id,
            Gift.claimed_by_id == user_id,
        )
        .order_by(GiftList.id, Gift.id)
    ).all()
    return [
        {
            "id": gift.id,
            "name": gift.name,
            "description": gift.description,
            "url": gift.url,
            "price": gift.price,
            "list_id": gift.list_id,
            "list_name": list_name,
            "purchased_at": gift.purchased_at,
        }
        for gift, list_name in rows
    ]
