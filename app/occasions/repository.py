from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Row, delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.list_occasion_share import ListOccasionShare
from app.models.occasion import Occasion
from app.models.occasion_archive_prompt import OccasionArchivePrompt


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


def shared_activity_at_expr():
    """When an occasion was last busy **for everyone at once** — as SQL.

        max(last share into the occasion, occasion.created_at)

    This is the clock the archive nudge ages an occasion by, and it reads **no
    claim at all — not even the caller's own**. That is the whole of it, and the
    absent `user_id` parameter is the guarantee: there is no argument here that
    could widen this to a claim, and the signature says so at every call site.

    The obvious choice was the per-viewer clock below — ADR 0005 and the M1
    contract both say the nudge would filter on it — and it is wrong here, for
    NEU-1292's reason arrived at from the other side. Under the per-viewer
    clock, eligibility turns on the caller's own claims, so two members disagree
    about whether the same occasion is stale. That much is defensible. The
    *shared* half of the disagreement is not: consider a family occasion holding
    only Gran's own wishlist, untouched for seventy days. Gran is nudged. Tom
    claims a gift from her list today. If eligibility read anyone else's claims,
    Gran's prompt would vanish — and Gran would learn that somebody is buying
    her a present, and roughly when. That is `CONTEXT.md` invariant 1 broken by
    the *absence* of a banner row, which is exactly as invisible as ADR 0005's
    sort order and exactly as disclosive.

    Dropping the caller's own claims too costs nothing — they are safe to read —
    and buys a property worth having: **staleness is one fact about the
    occasion, identical for everyone eligible.** No user's action can create or
    destroy another user's prompt, so there is nothing left to infer.

    `created_at` stays the floor for NEU-1292's reason: an occasion created
    seventy days ago that nothing ever happened to is precisely the dead
    Christmas the nudge exists for, and a null clock would make the consumer
    decide what null means.
    """
    last_share = (
        select(func.max(ListOccasionShare.created_at))
        .where(ListOccasionShare.occasion_id == Occasion.id)
        .correlate(Occasion)
        .scalar_subquery()
    )
    return func.coalesce(last_share, Occasion.created_at, type_=DateTime())


def last_activity_at_expr(user_id: int):
    """When an occasion was last busy **for one viewer** — as SQL, not a value.

    The later of the last share into the occasion and *this viewer's own* last
    claim or purchase filed under it, floored at the occasion's creation:

        max(shared activity, my last claim, my last purchase)

    Its first term is `shared_activity_at_expr()` — the shares-and-creation half
    above — rather than a second copy of it. The two clocks cannot drift because
    one is literally built from the other, and the narrower one is the whole of
    what the archive nudge sees (ADR 0005, amended by NEU-1294).

    It returns an expression rather than a number because it is selected into
    this module's index alongside joins a plain value could not participate in.
    Defining it once is the whole point (ADR 0005): there is one place to read
    when "does this leak?" is asked again.

    **It must never read another user's claim.** The strip sorts on this value,
    so an occasion holding only the viewer's own list would rise to the top of
    their strip the moment somebody claimed from it — telling them that someone
    is buying them a present, and roughly when. That is `CONTEXT.md` invariant 1
    broken by a sort order rather than by a field, which is exactly why it does
    not look like a leak. A share is safe by contrast: the list it carries is
    already visible to every member of the family.

    Two spellings matter and neither is cosmetic:

    * The terms are **correlated scalar subqueries**, not joins. Joining
      `list_occasion_shares` and `claims` into one grouped query fans the rows
      out and multiplies the list count by the claim count.
    * Every term is **coalesced to `created_at` before** the comparison, because
      SQLite's scalar `max()` returns NULL if *any* argument is NULL — so the
      naive spelling yields a null clock for precisely the untouched occasion
      that must never have one. `shared_activity_at_expr()` already carries its
      own coalesce, which is why the first term below has none of its own.

    `claimed_at` and `purchased_at` are two aggregates combined out here rather
    than one nested `max()`: `purchased_at` is nullable and is not guaranteed to
    be the later of the two, since unticking a purchase keeps the amount and
    `PATCH /claims/{id}` can move a filing.

    The claim half is hand-written here rather than in `app/claims/repository.py`
    — the usual home for claim SQL — because it is one correlated aggregate of a
    query about occasions, and because ADR 0005 asks for the whole definition in
    a single readable place.
    """
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
        shared_activity_at_expr(),
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


def get_archive_prompts(
    db: Session, user_id: int, idle_days: int
) -> list[Row]:
    """Every occasion this caller should be asked to archive.

    Across every family they belong to, with no parameter of any kind: like
    `get_occasion_summaries`, the scope is the shape of the question rather than
    a check that could be forgotten. A caller with nothing to answer gets an
    empty list.

    Five terms, and each is here for its own reason:

    * **Not already archived.** The nudge asks a question that has been answered.
    * **Stale**, by `shared_activity_at_expr()` — which reads no claim, by
      anyone. See that function: eligibility that moved on somebody else's claim
      would disclose the claim by the prompt's *disappearance*.
    * **A member of the occasion's family.** A member can leave and
      `occasions.created_by_id` keeps pointing at them; leaving withdraws what
      membership granted, and the banner should never name a family the caller
      has left. It is also what makes the role term below readable at all.
    * **An organizer, or the occasion's creator.** Organizer-only would leave a
      member-created occasion in a family with an absent organizer permanently
      un-nudged — the dead Christmas the feature exists for — and the creator
      already had the authority to make it.
    * **No live dismissal.** A correlated `NOT EXISTS`, evaluated in SQL.

    **The snooze and the idle cutoff are both compared in the database, never in
    Python.** SQLAlchemy's SQLite `DATETIME` strips tzinfo on the way in and
    hands back naive values on the way out, so a `dismissed_until` read into
    Python and compared against `datetime.now(timezone.utc)` raises `TypeError:
    can't compare offset-naive and offset-aware datetimes`. Bound as parameters
    both sides are naive UTC strings, which compare correctly — and there is no
    per-call discipline to remember.

    Ordered `id DESC`: newest first, and stable. There is no clock in the
    payload to sort on, and there must not be one — a date on a prompt invites
    the next reader to assume it is `last_activity_at`, which it deliberately is
    not.
    """
    now = datetime.now(timezone.utc)
    idle_cutoff = now - timedelta(days=idle_days)
    live_dismissal = (
        select(OccasionArchivePrompt.id)
        .where(
            OccasionArchivePrompt.occasion_id == Occasion.id,
            OccasionArchivePrompt.user_id == user_id,
            OccasionArchivePrompt.dismissed_until > now,
        )
        .correlate(Occasion)
        .exists()
    )
    return list(
        db.execute(
            select(
                Occasion.id,
                Occasion.name,
                Occasion.family_id,
                Family.name.label("family_name"),
            )
            .join(Family, Family.id == Occasion.family_id)
            .join(FamilyMember, FamilyMember.family_id == Family.id)
            .where(
                FamilyMember.user_id == user_id,
                Occasion.is_archived.is_(False),
                shared_activity_at_expr() < idle_cutoff,
                or_(
                    FamilyMember.role == "organizer",
                    Occasion.created_by_id == user_id,
                ),
                ~live_dismissal,
            )
            .order_by(Occasion.id.desc())
        ).all()
    )


def upsert_dismissal(
    db: Session, *, user_id: int, occasion_id: int, dismissed_until: datetime
) -> None:
    """Record this caller's "not yet" against this occasion, or extend it.

    An upsert rather than an insert because `UNIQUE (user_id, occasion_id)`
    holds: a second dismissal once the first has lapsed must extend the snooze,
    not collide with the row that expired.
    """
    prompt = db.execute(
        select(OccasionArchivePrompt).where(
            OccasionArchivePrompt.user_id == user_id,
            OccasionArchivePrompt.occasion_id == occasion_id,
        )
    ).scalar_one_or_none()
    if prompt is None:
        db.add(
            OccasionArchivePrompt(
                user_id=user_id,
                occasion_id=occasion_id,
                dismissed_until=dismissed_until,
            )
        )
    else:
        prompt.dismissed_until = dismissed_until
    db.flush()


def delete_prompts_for_occasions(db: Session, occasion_ids: list[int]) -> None:
    """Every user's prompt row against these occasions.

    Called when a family — and with it its occasions — is deleted. SQLite runs
    with `PRAGMA foreign_keys=ON`, so a row left behind does not orphan itself:
    it refuses the delete outright. A snooze has nothing to survive for once its
    occasion is gone, exactly as a budget has not.
    """
    if not occasion_ids:
        return
    db.execute(
        delete(OccasionArchivePrompt).where(
            OccasionArchivePrompt.occasion_id.in_(occasion_ids)
        )
    )
    db.flush()


def delete_prompts_by_user(db: Session, user_id: int) -> None:
    """Every prompt row this user has dismissed, anywhere."""
    db.execute(
        delete(OccasionArchivePrompt).where(
            OccasionArchivePrompt.user_id == user_id
        )
    )
    db.flush()
