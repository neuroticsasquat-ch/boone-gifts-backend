from decimal import Decimal

from sqlalchemy.orm import Session

from app.access import can_view_list
from app.budgets import service as budgets_service
from app.claims import repository as claims_repo
from app.families import repository as families_repo
from app.family_invites.service import _require_organizer
from app.list_occasions import repository as list_occasions_repo
from app.lists import service as list_service
from app.models.family_member import FamilyMember
from app.models.occasion import Occasion
from app.models.user import User
from app.occasions import repository as repo
from app.schemas.gift_list import GiftListRead, GiftListViewerRead
from app.services.exceptions import ForbiddenError, NotFoundError

ORGANIZER_ONLY = "Only organizers can rename or archive an occasion."


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
    """Rename or (un)archive an occasion. Organizer-only.

    Renaming changes a label everyone sees and everyone's budgets are filed
    under, so it matches every other family-wide action in `families/service.py`.
    """
    occasion = repo.get_occasion(db, occasion_id)
    if occasion is None:
        raise NotFoundError("Occasion not found.")
    _require_organizer(db, occasion.family_id, actor, message=ORGANIZER_ONLY)
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
    return [
        list_service.to_summary(gift_list, actor.id)
        for gift_list in list_occasions_repo.get_lists_shared_to_occasion(
            db, occasion_id
        )
        if can_view_list(db, actor, gift_list)
    ]


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
