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
