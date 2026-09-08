from sqlalchemy.orm import Session

from app.families import repository as families_repo
from app.family_invites.service import _require_organizer
from app.models.family_member import FamilyMember
from app.models.occasion import Occasion
from app.models.user import User
from app.occasions import repository as repo
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
