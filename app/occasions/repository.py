from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.occasion import Occasion


def create_occasion(
    db: Session, family_id: int, name: str, created_by_id: int
) -> Occasion:
    occasion = Occasion(
        family_id=family_id, name=name, created_by_id=created_by_id
    )
    db.add(occasion)
    db.flush()
    return occasion


def get_occasion(db: Session, occasion_id: int) -> Occasion | None:
    return db.get(Occasion, occasion_id)


def get_occasions_for_family(
    db: Session, family_id: int, archived: bool
) -> list[Occasion]:
    return list(
        db.execute(
            select(Occasion)
            .where(
                Occasion.family_id == family_id,
                Occasion.is_archived == archived,
            )
            .order_by(Occasion.id)
        )
        .scalars()
        .all()
    )


def has_active_occasion(db: Session, family_id: int) -> bool:
    return (
        db.execute(
            select(Occasion.id)
            .where(
                Occasion.family_id == family_id,
                Occasion.is_archived.is_(False),
            )
            .limit(1)
        ).first()
        is not None
    )


def update_occasion(db: Session, occasion: Occasion, update_data: dict) -> Occasion:
    for key, value in update_data.items():
        setattr(occasion, key, value)
    db.flush()
    return occasion


def get_occasion_ids_for_family(db: Session, family_id: int) -> list[int]:
    """Every occasion of one family, archived included — the callers that use
    this are unwinding the family, and archiving is not deletion."""
    return list(
        db.execute(
            select(Occasion.id).where(Occasion.family_id == family_id)
        ).scalars().all()
    )


def delete_occasions_for_family(db: Session, family_id: int) -> None:
    db.execute(delete(Occasion).where(Occasion.family_id == family_id))
