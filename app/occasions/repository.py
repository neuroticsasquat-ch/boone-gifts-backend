from sqlalchemy import DateTime, Row, delete, func, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.list_occasion_share import ListOccasionShare
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


def last_activity_at_expr(user_id: int):
    """When an occasion was last busy **for one viewer** — as SQL, not a value.

    The later of the last share into the occasion and *this viewer's own* last
    claim or purchase filed under it, floored at the occasion's creation:

        max(last share in, my last claim, my last purchase, created_at)

    It returns an expression rather than a number because two features need the
    same clock in two different places — this module's index selects it, and
    M4's archive nudge filters on it in the database, beside joins this endpoint
    has no use for. Defining it once is the whole point (ADR 0005): there is one
    place to read when "does this leak?" is asked again.

    **It must never read another user's claim.** The strip sorts on this value,
    so an occasion holding only the viewer's own list would rise to the top of
    their strip the moment somebody claimed from it — telling them that someone
    is buying them a present, and roughly when. That is `CONTEXT.md` invariant 1
    broken by a sort order rather than by a field, which is exactly why it does
    not look like a leak. A share is safe by contrast: the list it carries is
    already visible to every member of the family.

    Two spellings matter and neither is cosmetic:

    * The three terms are **correlated scalar subqueries**, not joins. Joining
      `list_occasion_shares` and `claims` into one grouped query fans the rows
      out and multiplies the list count by the claim count.
    * Every term is **coalesced to `created_at` before** the comparison, because
      SQLite's scalar `max()` returns NULL if *any* argument is NULL — so the
      naive spelling yields a null clock for precisely the untouched occasion
      that must never have one.

    `claimed_at` and `purchased_at` are two aggregates combined out here rather
    than one nested `max()`: `purchased_at` is nullable and is not guaranteed to
    be the later of the two, since unticking a purchase keeps the amount and
    `PATCH /claims/{id}` can move a filing.

    The claim half is hand-written here rather than in `app/claims/repository.py`
    — the usual home for claim SQL — because it is one correlated aggregate of a
    query about occasions, and because ADR 0005 asks for the whole definition in
    a single readable place that M4 embeds verbatim.
    """
    last_share = (
        select(func.max(ListOccasionShare.created_at))
        .where(ListOccasionShare.occasion_id == Occasion.id)
        .correlate(Occasion)
        .scalar_subquery()
    )
    my_last_claim = (
        select(func.max(Claim.claimed_at))
        .where(Claim.occasion_id == Occasion.id, Claim.user_id == user_id)
        .correlate(Occasion)
        .scalar_subquery()
    )
    my_last_purchase = (
        select(func.max(Claim.purchased_at))
        .where(Claim.occasion_id == Occasion.id, Claim.user_id == user_id)
        .correlate(Occasion)
        .scalar_subquery()
    )
    return func.max(
        func.coalesce(last_share, Occasion.created_at),
        func.coalesce(my_last_claim, Occasion.created_at),
        func.coalesce(my_last_purchase, Occasion.created_at),
        type_=DateTime(),
    )


def get_occasion_summaries(
    db: Session, user_id: int, archived: bool
) -> list[Row]:
    """Every occasion in every family this user belongs to, with its counts.

    Scoped by the caller's memberships through the join, so an occasion they
    cannot see is not a row that gets filtered out — it is a row that never
    exists. A caller in no families therefore gets `[]` rather than a 404, and
    there is no per-occasion membership check to forget.

    `list_count` counts the share rows directly instead of filtering each list
    through `can_view_list`, as `service.list_lists` does. The two are provably
    equal here — that predicate's occasion arm is "shared to an occasion of a
    family the viewer belongs to", and the caller is a member of this occasion's
    family or the row would not exist — and running it per list across every
    occasion of every family is the exact fan-out this endpoint was written to
    kill, on the app's landing page. A test pins `list_count` to what
    `GET /occasions/{id}/lists` returns, so a new term in `can_view_list` fails
    loudly rather than leaving the card quietly lying.

    The two `my_*` counts key on the stored filing alone — no join back to the
    shares — exactly as the occasion's My shopping tab and its budget line do
    (`get_shopping_for_occasion`, `get_spend_for_occasion`), so a card cannot
    contradict the tab printed beneath it. One consequence is deliberate: a
    claim outlives its list being unshared, so an occasion with no lists can
    legitimately report claims.

    Ordered on the clock, with an `id` tiebreak — two occasions created in the
    same transaction share `created_at` to the second, so without it the order
    is whatever the query plan yields and two members of a family can see the
    strip differently for no reason.
    """
    list_count = (
        select(func.count(ListOccasionShare.id))
        .where(ListOccasionShare.occasion_id == Occasion.id)
        .correlate(Occasion)
        .scalar_subquery()
    )
    my_claimed_count = (
        select(func.count(Claim.id))
        .where(Claim.occasion_id == Occasion.id, Claim.user_id == user_id)
        .correlate(Occasion)
        .scalar_subquery()
    )
    # `count` over the nullable column counts the purchases, mirroring
    # `_spend_select`'s `bought_count`: claimed and bought are driven off
    # different columns on purpose.
    my_bought_count = (
        select(func.count(Claim.purchased_at))
        .where(Claim.occasion_id == Occasion.id, Claim.user_id == user_id)
        .correlate(Occasion)
        .scalar_subquery()
    )
    last_activity_at = last_activity_at_expr(user_id).label("last_activity_at")
    return list(
        db.execute(
            select(
                Occasion.id,
                Occasion.family_id,
                Occasion.name,
                Occasion.is_archived,
                Occasion.created_by_id,
                Occasion.created_at,
                Occasion.updated_at,
                Family.name.label("family_name"),
                list_count.label("list_count"),
                my_claimed_count.label("my_claimed_count"),
                my_bought_count.label("my_bought_count"),
                last_activity_at,
            )
            .join(Family, Family.id == Occasion.family_id)
            .join(FamilyMember, FamilyMember.family_id == Family.id)
            .where(
                FamilyMember.user_id == user_id,
                Occasion.is_archived == archived,
            )
            .order_by(last_activity_at.desc(), Occasion.id.desc())
        ).all()
    )
