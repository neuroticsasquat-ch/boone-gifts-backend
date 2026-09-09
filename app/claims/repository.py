"""Every query that touches a claim.

The claim is its own entity now (ADR 0003), so it gets its own repository
rather than a claim-shaped query in each domain that has to unwind one. The
teardown callers — connections, families, list occasions, users — reach for
these instead of writing claim SQL of their own.
"""
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.gift import Gift
from app.models.gift_list import GiftList


def get_claim_for_gift(db: Session, gift_id: int) -> Claim | None:
    return db.execute(
        select(Claim).where(Claim.gift_id == gift_id)
    ).scalar_one_or_none()


def create_claim(
    db: Session, gift_id: int, user_id: int, occasion_id: int | None = None
) -> Claim | None:
    """Claim a gift, or return None if somebody else got there first.

    Claiming is competitive, so the losing caller has to be told apart from an
    error. `uq_claims_gift` is what actually decides it — checking first and
    inserting second would leave a window where both callers win.
    """
    claim = Claim(
        gift_id=gift_id,
        user_id=user_id,
        occasion_id=occasion_id,
        claimed_at=datetime.now(timezone.utc),
    )
    try:
        # A SAVEPOINT, so losing the race unwinds this insert and nothing else.
        # A plain rollback here would discard the caller's whole transaction.
        with db.begin_nested():
            db.add(claim)
            db.flush()
    except IntegrityError:
        return None
    return claim


def update_claim(db: Session, claim: Claim, updates: dict) -> Claim:
    for field, value in updates.items():
        setattr(claim, field, value)
    db.flush()
    return claim


def delete_claim(db: Session, claim: Claim) -> None:
    db.delete(claim)
    db.flush()


def has_claimed_gifts(db: Session, list_id: int) -> bool:
    gift_ids = select(Gift.id).where(Gift.list_id == list_id)
    return (
        db.execute(
            select(Claim.id).where(Claim.gift_id.in_(gift_ids)).limit(1)
        ).first()
        is not None
    )


def any_claims_by_users(db: Session, list_id: int, user_ids: list[int]) -> bool:
    if not user_ids:
        return False
    gift_ids = select(Gift.id).where(Gift.list_id == list_id)
    return (
        db.execute(
            select(Claim.id)
            .where(Claim.gift_id.in_(gift_ids), Claim.user_id.in_(user_ids))
            .limit(1)
        ).first()
        is not None
    )


def unclaim_for_users(db: Session, list_id: int, user_ids: list[int]) -> None:
    """Release the claims those users hold on one list. The rows go, and the
    purchase state and amount paid go with them — there is nothing left to
    reset by hand."""
    if not user_ids:
        return
    gift_ids = select(Gift.id).where(Gift.list_id == list_id)
    db.execute(
        delete(Claim).where(
            Claim.gift_id.in_(gift_ids), Claim.user_id.in_(user_ids)
        )
    )
    db.flush()


def unclaim_gifts_between(db: Session, user_a_id: int, user_b_id: int) -> None:
    """Release each user's claims on the other's lists, both directions."""
    lists_a = select(GiftList.id).where(GiftList.owner_id == user_a_id)
    lists_b = select(GiftList.id).where(GiftList.owner_id == user_b_id)
    gifts_a = select(Gift.id).where(Gift.list_id.in_(lists_a))
    gifts_b = select(Gift.id).where(Gift.list_id.in_(lists_b))

    db.execute(
        delete(Claim).where(Claim.gift_id.in_(gifts_a), Claim.user_id == user_b_id)
    )
    db.execute(
        delete(Claim).where(Claim.gift_id.in_(gifts_b), Claim.user_id == user_a_id)
    )
    db.flush()


def delete_claims_by_user(db: Session, user_id: int) -> None:
    """Every claim this user holds, anywhere."""
    db.execute(delete(Claim).where(Claim.user_id == user_id))
    db.flush()


def delete_claims_on_lists(db: Session, list_ids: list[int]) -> None:
    """Every claim anyone holds on these lists' gifts. Claims hold a foreign key
    into `gifts`, so they have to go before the gifts do."""
    if not list_ids:
        return
    gift_ids = select(Gift.id).where(Gift.list_id.in_(list_ids))
    db.execute(delete(Claim).where(Claim.gift_id.in_(gift_ids)))
    db.flush()
