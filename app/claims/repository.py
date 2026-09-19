"""Every query that touches a claim.

The claim is its own entity now (ADR 0003), so it gets its own repository
rather than a claim-shaped query in each domain that has to unwind one. The
teardown callers — connections, families, list occasions, users — reach for
these instead of writing claim SQL of their own.
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.budgets.giftees import key_for_triple
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


# The three columns a giftee is derived from (ADR 0006). One tuple, so the
# shopping projection, the per-giftee grouping and the key all read the same
# definition.
_GIFTEE_COLUMNS = (
    GiftList.owner_id,
    GiftList.account_person_id,
    GiftList.recipient_name,
)


def _shopping_select():
    """The shopping row, minus the scope that selects it.

    Both shopping tabs read the same thing — the caller's own claims and the
    gifts they stand on — and differ only in what bounds the set: an occasion
    the claims are *filed under*, or a folder the lists are *in*. One select,
    two `where` clauses, so a column added to the payload lands on both tabs.

    The join runs claim → gift → list, never the reverse, so a gift with no
    claim cannot appear. Ordering by list and then gift keeps every reload
    returning the same sequence; the client groups on `giftee_key`, which the
    row derives from the list's three giftee columns (NEU-1326).
    """
    return (
        select(Claim, Gift, GiftList.name.label("list_name"), *_GIFTEE_COLUMNS)
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
            "giftee_key": key_for_triple(owner_id, account_person_id, recipient_name),
            "purchased_at": claim.purchased_at,
            "amount_paid": claim.amount_paid,
        }
        for claim, gift, list_name, owner_id, account_person_id, recipient_name
        in db.execute(statement).all()
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


def _claimed_lists_select():
    """The distinct lists the caller's shopping rows stand on — source 2 of the
    giftee set (NEU-1326 decision 3). Filing is stored, not derived, so a claim
    on a since-unshared list still shows on the tab, and its giftee must have a
    group to sit in. Same join direction as `_shopping_select`."""
    return (
        select(GiftList)
        .join(Gift, Gift.list_id == GiftList.id)
        .join(Claim, Claim.gift_id == Gift.id)
        .distinct()
    )


def get_claimed_lists_for_occasion(
    db: Session, occasion_id: int, user_id: int
) -> list[GiftList]:
    return list(
        db.execute(
            _claimed_lists_select().where(
                Claim.occasion_id == occasion_id,
                Claim.user_id == user_id,
            )
        )
        .scalars()
        .all()
    )


def get_claimed_lists_for_folder(
    db: Session, folder_id: int, user_id: int
) -> list[GiftList]:
    return list(
        db.execute(
            _claimed_lists_select()
            .join(FolderItem, FolderItem.list_id == GiftList.id)
            .where(
                FolderItem.folder_id == folder_id,
                Claim.user_id == user_id,
            )
        )
        .scalars()
        .all()
    )


# The four aggregates a budget line is made of, as module-level expressions so
# the overall select and the per-giftee select read one definition rather than
# a copy each (NEU-1326 decision 4). Their semantics are documented once, on
# `_spend_select`.
_TOTAL_COUNT = func.count(Claim.id).label("total_count")
_BOUGHT_COUNT = func.count(Claim.purchased_at).label("bought_count")
_SPENT = func.coalesce(
    func.sum(
        case(
            (Claim.purchased_at.isnot(None), Claim.amount_paid),
            else_=0,
        )
    ),
    0,
).label("spent")
_UNPRICED_COUNT = func.coalesce(
    func.sum(
        case(
            (
                Claim.purchased_at.isnot(None) & Claim.amount_paid.is_(None),
                1,
            ),
            else_=0,
        )
    ),
    0,
).label("unpriced_count")


def _spend_select():
    """The four numbers a budget line is made of, minus the scope.

    Counted over the caller's own claims and no one else's — same rule, same
    reason as `_shopping_select`, which this deliberately mirrors so the tally
    and the rows beneath it can never describe different sets.

    `spent` sums `amount_paid` alone: a purchase with no amount recorded is
    counted as bought and reported as unpriced, but never guessed at from the
    owner's asking price. That is what lets a client state an understated total
    as an understatement (project spec §7).

    **Spend follows the tick** (NEU-1325). The sum is gated on `purchased_at`,
    the same column `bought_count` and `unpriced_count` read, so an amount
    sitting on a claim that is not ticked bought — held by unticking so
    re-ticking need not retype it, or written straight on by
    `PATCH /claims/{id}` — counts as nothing until the claim is ticked again.
    An unticked gift is one the claimer has said they have *not* bought, and a
    budget line that charges them for it is wrong, not cautious. The amount is
    still stored on the claim and still travels on the shopping row; only the
    total ignores it.
    """
    return select(_TOTAL_COUNT, _BOUGHT_COUNT, _SPENT, _UNPRICED_COUNT).join(
        Gift, Claim.gift_id == Gift.id
    )


def _spend_from(row) -> dict:
    return {
        "total_count": row.total_count,
        "bought_count": row.bought_count,
        "spent": Decimal(row.spent),
        "unpriced_count": row.unpriced_count,
    }


def _spend_row(db: Session, statement) -> dict:
    return _spend_from(db.execute(statement).one())


def get_spend_for_occasion(db: Session, occasion_id: int, user_id: int) -> dict:
    """What the caller has spent against one occasion, and on how many gifts.

    Keyed on the stored filing, exactly as the occasion shopping tab is, so the
    budget line counts the rows the tab shows and nothing else.
    """
    return _spend_row(
        db,
        _spend_select().where(
            Claim.occasion_id == occasion_id,
            Claim.user_id == user_id,
        ),
    )


def get_spend_for_folder(db: Session, folder_id: int, user_id: int) -> dict:
    """What the caller has spent on gifts in the lists this folder holds."""
    return _spend_row(
        db,
        _spend_select()
        .join(GiftList, Gift.list_id == GiftList.id)
        .join(FolderItem, FolderItem.list_id == GiftList.id)
        .where(
            FolderItem.folder_id == folder_id,
            Claim.user_id == user_id,
        ),
    )


def _spend_by_giftee_select():
    """`_spend_select`, grouped by the giftee the list is for (NEU-1326).

    The same four aggregates, so spend-follows-the-tick and the unpriced
    disclosure are inherited rather than copied; the sum across groups equals
    the overall's figures by construction, because both count the same rows.
    """
    return (
        select(
            *_GIFTEE_COLUMNS, _TOTAL_COUNT, _BOUGHT_COUNT, _SPENT, _UNPRICED_COUNT
        )
        .join(Gift, Claim.gift_id == Gift.id)
        .join(GiftList, Gift.list_id == GiftList.id)
        .group_by(*_GIFTEE_COLUMNS)
    )


def _spend_by_giftee(db: Session, statement) -> dict[str, dict]:
    return {
        key_for_triple(
            row.owner_id, row.account_person_id, row.recipient_name
        ): _spend_from(row)
        for row in db.execute(statement).all()
    }


def get_spend_by_giftee_for_occasion(
    db: Session, occasion_id: int, user_id: int
) -> dict[str, dict]:
    """The caller's spend under one occasion, split by giftee key."""
    return _spend_by_giftee(
        db,
        _spend_by_giftee_select().where(
            Claim.occasion_id == occasion_id,
            Claim.user_id == user_id,
        ),
    )


def get_spend_by_giftee_for_folder(
    db: Session, folder_id: int, user_id: int
) -> dict[str, dict]:
    """The caller's spend on the folder's lists, split by giftee key."""
    return _spend_by_giftee(
        db,
        _spend_by_giftee_select()
        .join(FolderItem, FolderItem.list_id == GiftList.id)
        .where(
            FolderItem.folder_id == folder_id,
            Claim.user_id == user_id,
        ),
    )
