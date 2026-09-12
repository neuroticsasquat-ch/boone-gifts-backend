from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Row
from sqlalchemy.orm import Session

from app.access import can_view_list
from app.budgets import service as budgets_service
from app.claims import repository as claims_repo
from app.families import repository as families_repo
from app.list_occasions import repository as list_occasions_repo
from app.lists import service as list_service
from app.models.family_member import FamilyMember
from app.models.occasion import Occasion
from app.models.user import User
from app.occasions import repository as repo
from app.schemas.gift_list import GiftListRead, GiftListViewerRead
from app.services.exceptions import ForbiddenError, NotFoundError

ORGANIZER_ONLY = "Only organizers can rename an occasion."
ORGANIZER_OR_CREATOR = (
    "Only organizers or the occasion's creator can archive an occasion."
)

# Product rules from the project spec §8, not deployment knobs — mirroring
# `INVITE_EXPIRY_DAYS` in `app/family_invites/service.py`. A per-environment
# threshold would make the dev seed's stale fixture depend on config.
ARCHIVE_PROMPT_IDLE_DAYS = 60
ARCHIVE_PROMPT_SNOOZE_DAYS = 30


def _require_member(db: Session, family_id: int, actor: User) -> FamilyMember:
    """Any member of the family may read and create its occasions (ADR 0002)."""
    family = families_repo.get_family(db, family_id)
    if family is None:
        raise NotFoundError("Family not found.")
    membership = families_repo.get_family_member(
        db, family_id=family_id, user_id=actor.id
    )
    if membership is None:
        raise ForbiddenError("Not a member of this family.")
    return membership


def _load_for_member(db: Session, occasion_id: int, actor: User) -> Occasion:
    occasion = repo.get_occasion(db, occasion_id)
    if occasion is None:
        raise NotFoundError("Occasion not found.")
    _require_member(db, occasion.family_id, actor)
    return occasion


def _may_archive(membership: FamilyMember, occasion: Occasion, actor: User) -> bool:
    """The archive nudge's audience: an organizer, or the occasion's creator.

    One predicate rather than two copies, because the eligibility query, the
    dismissal and the archive write must agree exactly — a user nudged to
    archive an occasion they then cannot archive is the bug the audience rule
    creates if these ever drift. Membership is the caller's already-loaded row,
    so this asks only the half that varies.
    """
    return membership.role == "organizer" or occasion.created_by_id == actor.id


def list_occasions(
    db: Session, family_id: int, actor: User, archived: bool
) -> list[Occasion]:
    _require_member(db, family_id, actor)
    return repo.get_occasions_for_family(db, family_id, archived=archived)


def create_occasion(
    db: Session, family_id: int, actor: User, name: str
) -> tuple[Occasion, bool]:
    """Create an occasion for the family. Any member may.

    A second active occasion is allowed — the caller is warned, not blocked, so
    nobody waits on an absent organizer while the family cannot be shared to.
    Returns the occasion and whether the family already had an active one.
    """
    _require_member(db, family_id, actor)
    has_other_active = repo.has_active_occasion(db, family_id)
    occasion = repo.create_occasion(
        db, family_id=family_id, name=name, created_by_id=actor.id
    )
    return occasion, has_other_active


def get_occasion(db: Session, occasion_id: int, actor: User) -> Occasion:
    return _load_for_member(db, occasion_id, actor)


def update_occasion(
    db: Session, occasion_id: int, actor: User, update_data: dict
) -> Occasion:
    """Rename or (un)archive an occasion. **Gated per field, not per endpoint.**

    | Field | Who |
    |---|---|
    | `name` | an organizer |
    | `is_archived` | an organizer, **or** the occasion's creator |

    Archiving *is* this endpoint with `is_archived`, so leaving the whole of it
    organizer-only would nudge a member who created an occasion to archive it
    and then answer 403 when they pressed the button. The project spec's
    justification for widening the audience — the creator already had the
    authority to make it — is true of creation and of archiving, and false of
    renaming: a rename changes a label everyone sees and every budget is filed
    under, while archiving is reversible, withdraws no shares and still serves
    every My shopping tab. It was the mildest write on an occasion carrying the
    strictest gate.

    The gate is on the **field, not the direction**: unarchiving carries the
    same rule, because a creator who can close an occasion by mistake must be
    able to reopen it. A request setting both fields at once needs the organizer
    role, because it contains a rename.

    Membership is required before either check, and for the empty update too —
    an occasion the caller cannot see must not answer 200 to a no-op.
    """
    occasion = repo.get_occasion(db, occasion_id)
    if occasion is None:
        raise NotFoundError("Occasion not found.")
    membership = _require_member(db, occasion.family_id, actor)
    if "name" in update_data and membership.role != "organizer":
        raise ForbiddenError(ORGANIZER_ONLY)
    if "is_archived" in update_data and not _may_archive(
        membership, occasion, actor
    ):
        raise ForbiddenError(ORGANIZER_OR_CREATOR)
    return repo.update_occasion(db, occasion, update_data)


def list_lists(
    db: Session, occasion_id: int, actor: User
) -> list[GiftListRead | GiftListViewerRead]:
    """The occasion's lists, as this member can see them.

    Every row goes through `can_view_list` even though membership of the
    occasion's family already implies it — that is the codebase's one visibility
    predicate (`CONTEXT.md` invariant 2), and routing through it means a term
    added there is inherited here instead of being quietly missed. The cost is
    one query per list on the occasion.
    """
    _load_for_member(db, occasion_id, actor)
    return list_service.to_summaries(
        db,
        [
            gift_list
            for gift_list in list_occasions_repo.get_lists_shared_to_occasion(
                db, occasion_id
            )
            if can_view_list(db, actor, gift_list)
        ],
        actor.id,
    )


def list_shopping(db: Session, occasion_id: int, actor: User) -> dict:
    """The caller's own claims filed under this occasion.

    Membership of the occasion's family is the gate, and the only one that is
    needed: the query is keyed on the caller's own user id, so there is no
    parameter, no admin path and no aggregate here that could return anyone
    else's claims (`CONTEXT.md` invariant 1).

    Archiving is not unsharing (§5.4), and a January shopper is still buying
    against December's occasion, so an archived occasion serves its payload
    unchanged — `_load_for_member` deliberately does not consult `is_archived`.

    The budget rollup rides along with the rows rather than sitting behind a
    second endpoint: the tab renders one screen, and a total fetched separately
    can contradict the list printed beneath it.
    """
    _load_for_member(db, occasion_id, actor)
    return {
        "budget": budgets_service.get_rollup(
            db, user_id=actor.id, occasion_id=occasion_id
        ),
        "items": claims_repo.get_shopping_for_occasion(db, occasion_id, actor.id),
    }


def set_budget(db: Session, occasion_id: int, actor: User, amount: Decimal) -> dict:
    """Set the caller's own budget for this occasion, and return the rollup.

    Membership is the gate and the whole of it. An organizer has no more say
    here than anyone else: they name the occasion, they never touch money and
    never see any (project spec §7).
    """
    _load_for_member(db, occasion_id, actor)
    return budgets_service.set_budget(
        db, user_id=actor.id, occasion_id=occasion_id, amount=amount
    )


def clear_budget(db: Session, occasion_id: int, actor: User) -> dict:
    _load_for_member(db, occasion_id, actor)
    return budgets_service.clear_budget(
        db, user_id=actor.id, occasion_id=occasion_id
    )


def list_all_occasions(db: Session, actor: User, archived: bool) -> list[Row]:
    """Every occasion the caller can see, across every family they belong to.

    Deliberately takes no family and no user parameter. The repository scopes
    the query by the caller's own memberships and keys both counts and the
    claim half of the clock on the caller's own id, so "you cannot read anyone
    else's counts" is the shape of the question rather than a check that could
    be forgotten (`CONTEXT.md` invariant 1, ADR 0005).

    There is no membership gate here for the same reason: an occasion the
    caller cannot see is not a row this query filters out, it is a row it never
    produces. A caller in no families gets an empty list, not a 404.
    """
    return repo.get_occasion_summaries(db, user_id=actor.id, archived=archived)


def list_archive_prompts(db: Session, actor: User) -> list[Row]:
    """Every occasion the caller should be asked to archive.

    Deliberately takes no parameter beyond the caller — no family, no user, no
    filter. The repository scopes the query by the caller's own memberships and
    keys the snooze on their own id, so "you cannot read anyone else's prompts"
    is the shape of the question rather than a check that could be forgotten
    (`CONTEXT.md` invariant 1).

    There is no membership gate here for the same reason `list_all_occasions`
    has none: an occasion the caller cannot see is not a row this query filters
    out, it is a row it never produces. A caller with nothing to answer gets an
    empty list, never a 404.
    """
    return repo.get_archive_prompts(
        db, user_id=actor.id, idle_days=ARCHIVE_PROMPT_IDLE_DAYS
    )


def dismiss_archive_prompt(db: Session, occasion_id: int, actor: User) -> None:
    """Record "not yet" against this occasion, for this caller alone.

    Re-checks the audience — membership, and organizer-or-creator — and
    **deliberately does not re-check staleness or the existing snooze.** The
    race is ordinary: the banner renders, somebody shares into the occasion, and
    only then does the user press Not yet. Refusing that call with a 409 would
    fail a button that was on screen, for a reason the user cannot explain, and
    would hand the banner an error branch that exists only to be swallowed.
    Anyone who could ever be nudged may record "not yet"; the worst case is a
    harmless row on an occasion that is no longer stale.

    The 30 days is the server's rule, which is why the endpoint takes no body.
    """
    occasion = repo.get_occasion(db, occasion_id)
    if occasion is None:
        raise NotFoundError("Occasion not found.")
    membership = _require_member(db, occasion.family_id, actor)
    if not _may_archive(membership, occasion, actor):
        raise ForbiddenError(ORGANIZER_OR_CREATOR)
    repo.upsert_dismissal(
        db,
        user_id=actor.id,
        occasion_id=occasion_id,
        dismissed_until=datetime.now(timezone.utc)
        + timedelta(days=ARCHIVE_PROMPT_SNOOZE_DAYS),
    )
