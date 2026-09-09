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
from app.models.folder_item import FolderItem
from app.models.gift import Gift
from app.models.gift_list import GiftList


def get_claim(db: Session, claim_id: int) -> Claim | None:
    return db.get(Claim, claim_id)


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


def _shopping_select():
    """The shopping row, minus the scope that selects it.

    Both shopping tabs read the same thing — the caller's own claims and the
    gifts they stand on — and differ only in what bounds the set: an occasion
    the claims are *filed under*, or a folder the lists are *in*. One select,
    two `where` clauses, so a column added to the payload lands on both tabs.

    The join runs claim → gift → list, never the reverse, so a gift with no
    claim cannot appear. Ordering by list and then gift is what "grouped by
    list, stable order" means: the client groups on `list_id` and every reload
    returns the same sequence.
    """
    return (
        select(Claim, Gift, GiftList.name.label("list_name"))
        .join(Gift, Claim.gift_id == Gift.id)
        .join(GiftList, Gift.list_id == GiftList.id)
        .order_by(GiftList.id, Gift.id)
    )


def _shopping_rows(db: Session, statement) -> list[dict]:
    return [
        {
            "claim_id": claim.id,
            "gift_id": gift.id,
            "name": gift.name,
            "description": gift.description,
            "url": gift.url,
            "price": gift.price,
            "list_id": gift.list_id,
            "list_name": list_name,
            "purchased_at": claim.purchased_at,
            "amount_paid": claim.amount_paid,
        }
        for claim, gift, list_name in db.execute(statement).all()
    ]


def get_shopping_for_occasion(
    db: Session, occasion_id: int, user_id: int
) -> list[dict]:
    """The caller's own claims filed under one occasion.

    Keyed on the stored filing alone — no join back to the shares. Filing is
    stored, not derived (ADR 0003), so a claim whose list was later unshared,
    or whose occasion was archived, still belongs on the tab it was filed
    under; re-deriving it here is exactly the budget that rewrites its own
    history.
    """
    return _shopping_rows(
        db,
        _shopping_select().where(
            Claim.occasion_id == occasion_id,
            Claim.user_id == user_id,
        ),
    )


def get_shopping_for_folder(db: Session, folder_id: int, user_id: int) -> list[dict]:
    """The caller's own claims on gifts in the lists this folder holds.

    Scoped by folder membership rather than by a filing: a folder is the
    claimer's own curation, and it is the only route to a claim on a directly
    shared list, which belongs to no occasion (project spec §9.4).
    """
    return _shopping_rows(
        db,
        _shopping_select()
        .join(FolderItem, FolderItem.list_id == GiftList.id)
        .where(
            FolderItem.folder_id == folder_id,
            Claim.user_id == user_id,
        ),
    )
