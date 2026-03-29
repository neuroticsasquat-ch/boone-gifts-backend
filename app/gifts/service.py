from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.gifts import repository as repo
from app.models.gift import Gift
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError


def _get_gift_for_list(db: Session, gift_id: int, list_id: int) -> Gift:
    gift = repo.get_gift_by_id(db, gift_id)
    if gift is None or gift.list_id != list_id:
        raise NotFoundError("Gift not found.")
    return gift


def create_gift(
    db: Session,
    list_id: int,
    name: str,
    description: str | None,
    url: str | None,
    price=None,
) -> Gift:
    return repo.create_gift(db, list_id, name, description, url, price)


def update_gift(
    db: Session, gift_id: int, list_id: int, updates: dict
) -> Gift:
    gift = _get_gift_for_list(db, gift_id, list_id)
    return repo.update_gift(db, gift, updates)


def delete_gift(db: Session, gift_id: int, list_id: int) -> None:
    gift = _get_gift_for_list(db, gift_id, list_id)
    if gift.claimed_by_id is not None:
        raise ConflictError("This gift cannot be deleted right now.")
    repo.delete_gift(db, gift)


def claim_gift(
    db: Session, gift_id: int, list_id: int, owner_id: int, user_id: int
) -> Gift:
    if owner_id == user_id:
        raise ForbiddenError("Cannot claim your own gift.")
    gift = _get_gift_for_list(db, gift_id, list_id)
    if gift.claimed_by_id is not None:
        raise ConflictError("Gift already claimed.")
    gift.claimed_by_id = user_id
    gift.claimed_at = datetime.now(timezone.utc)
    db.flush()
    return gift


def unclaim_gift(
    db: Session, gift_id: int, list_id: int, user_id: int
) -> Gift:
    gift = _get_gift_for_list(db, gift_id, list_id)
    if gift.claimed_by_id != user_id:
        raise ForbiddenError("Only the claimer can unclaim.")
    gift.claimed_by_id = None
    gift.claimed_at = None
    db.flush()
    return gift
