from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.claims import repository as claims_repo
from app.gifts import repository as repo
from app.lists import repository as list_repo
from app.models.claim import Claim
from app.models.gift import Gift
from app.services.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError


def _get_gift_for_list(db: Session, gift_id: int, list_id: int) -> Gift:
    gift = repo.get_gift_by_id(db, gift_id)
    if gift is None or gift.list_id != list_id:
        raise NotFoundError("Gift not found.")
    return gift


def _get_own_claim(db: Session, gift: Gift, user_id: int, action: str) -> Claim:
    claim = claims_repo.get_claim_for_gift(db, gift.id)
    if claim is None or claim.user_id != user_id:
        raise ForbiddenError(f"Only the claimer can {action}.")
    return claim


def create_gift(
    db: Session,
    list_id: int,
    name: str,
    description: str | None,
    url: str | None,
    price=None,
) -> Gift:
    return repo.create_gift(db, list_id, name, description, url, price)


def update_gift(db: Session, gift_id: int, list_id: int, updates: dict) -> Gift:
    gift = _get_gift_for_list(db, gift_id, list_id)
    return repo.update_gift(db, gift, updates)


def delete_gift(db: Session, gift_id: int, list_id: int) -> None:
    gift = _get_gift_for_list(db, gift_id, list_id)
    if claims_repo.get_claim_for_gift(db, gift_id) is not None:
        raise ConflictError(
            "This gift has been claimed by someone and cannot be deleted."
        )
    repo.delete_gift(db, gift)


def claim_gift(
    db: Session, gift_id: int, list_id: int, owner_id: int, user_id: int
) -> Gift:
    if owner_id == user_id:
        raise ForbiddenError("Cannot claim your own gift.")
    gift = _get_gift_for_list(db, gift_id, list_id)
    gift_list = list_repo.get_list_by_id(db, list_id)
    if gift_list and gift_list.is_archived:
        raise BadRequestError("Cannot claim gifts on an archived list.")
    # Filed under no occasion: resolving the filing is NEU-1269's job, and a
    # claim is a fact about the gift with or without one.
    claim = claims_repo.create_claim(db, gift_id, user_id)
    if claim is None:
        raise ConflictError("Gift already claimed.")
    db.refresh(gift)
    return gift


def unclaim_gift(db: Session, gift_id: int, list_id: int, user_id: int) -> Gift:
    """Release a claim. The row goes, so the purchase and the amount paid go
    with it — there is no purchase state left over to reset."""
    gift = _get_gift_for_list(db, gift_id, list_id)
    gift_list = list_repo.get_list_by_id(db, list_id)
    if gift_list and gift_list.is_archived:
        raise BadRequestError("Cannot unclaim gifts on an archived list.")
    claim = _get_own_claim(db, gift, user_id, "unclaim")
    claims_repo.delete_claim(db, claim)
    db.refresh(gift)
    return gift


def purchase_gift(
    db: Session, gift_id: int, list_id: int, user_id: int, updates: dict
) -> Gift:
    """Mark a claim purchased, optionally recording what it cost.

    `updates` is `model_dump(exclude_unset=True)`: an absent `amount_paid` keeps
    whatever is already recorded, which is what makes unticking and re-ticking
    non-destructive. Skipping the amount is a legitimate answer, so an explicit
    null clears it.
    """
    gift = _get_gift_for_list(db, gift_id, list_id)
    claim = _get_own_claim(db, gift, user_id, "mark as purchased")
    updates = dict(updates)
    updates["purchased_at"] = datetime.now(timezone.utc)
    claims_repo.update_claim(db, claim, updates)
    db.refresh(gift)
    return gift


def unpurchase_gift(db: Session, gift_id: int, list_id: int, user_id: int) -> Gift:
    """Untick purchased. `amount_paid` deliberately stays: the claim is still
    standing, and re-ticking should not make the user retype what they paid."""
    gift = _get_gift_for_list(db, gift_id, list_id)
    claim = _get_own_claim(db, gift, user_id, "unmark as purchased")
    claims_repo.update_claim(db, claim, {"purchased_at": None})
    db.refresh(gift)
    return gift
