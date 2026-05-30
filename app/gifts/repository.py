from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.gift import Gift


def create_gift(
    db: Session,
    list_id: int,
    name: str,
    description: str | None,
    url: str | None,
    price=None,
) -> Gift:
    gift = Gift(
        list_id=list_id,
        name=name,
        description=description,
        url=url,
        price=price,
    )
    db.add(gift)
    db.flush()
    return gift


def get_gift_by_id(db: Session, gift_id: int) -> Gift | None:
    return db.get(Gift, gift_id)


def update_gift(db: Session, gift: Gift, updates: dict) -> Gift:
    for field, value in updates.items():
        setattr(gift, field, value)
    db.flush()
    return gift


def delete_gift(db: Session, gift: Gift) -> None:
    db.delete(gift)
    db.flush()


def claim_gift(db: Session, gift_id: int, user_id: int) -> int:
    result = db.execute(
        update(Gift)
        .where(Gift.id == gift_id, Gift.claimed_by_id.is_(None))
        .values(claimed_by_id=user_id, claimed_at=datetime.now(timezone.utc))
    )
    db.flush()
    return result.rowcount


def unclaim_gift(db: Session, gift_id: int, user_id: int) -> int:
    result = db.execute(
        update(Gift)
        .where(Gift.id == gift_id, Gift.claimed_by_id == user_id)
        .values(claimed_by_id=None, claimed_at=None)
    )
    db.flush()
    return result.rowcount
