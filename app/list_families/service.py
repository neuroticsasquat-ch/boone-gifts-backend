from sqlalchemy.orm import Session

from app.families import repository as families_repo
from app.list_families import repository as repo
from app.models.gift_list import GiftList
from app.models.user import User
from app.services.exceptions import ConflictError, ForbiddenError

SIMPLE_MODE_MESSAGE = "Switch to full mode to manage family sharing for this list."
CLAIMED_MESSAGE = "Some gifts on this list are claimed by members of this family."


def _require_full_mode(user: User) -> None:
    if user.simple_mode:
        raise ForbiddenError(SIMPLE_MODE_MESSAGE)


def _require_membership(db: Session, user_id: int, family_id: int) -> None:
    if families_repo.get_family_member(db, family_id=family_id, user_id=user_id) is None:
        raise ForbiddenError("Not a member of this family.")


def list_family_states(db: Session, gift_list: GiftList) -> list[dict]:
    """Every family the list's owner belongs to, each flagged with whether the
    list is shared with it. Readable in both modes."""
    granted = repo.granted_family_ids(db, gift_list.id)
    families = repo.get_families_for_user(db, gift_list.owner_id)
    return [
        {"id": family.id, "name": family.name, "shared": family.id in granted}
        for family in families
    ]


def create_grant(db: Session, gift_list: GiftList, family_id: int, user: User) -> None:
    _require_full_mode(user)
    _require_membership(db, user.id, family_id)
    if repo.find_grant(db, gift_list.id, family_id) is None:
        repo.create_grant(db, gift_list.id, family_id)


def revoke_grant(
    db: Session,
    gift_list: GiftList,
    family_id: int,
    user: User,
    claims: str | None = None,
) -> None:
    """Revoke a family's grant on a list.

    With no `claims` choice, a family member holding a claim they would lose
    blocks the revoke with a ConflictError and nothing changes. `release`
    unclaims for members who lose every view path; `keep` leaves those claims
    standing. Collection items are deleted for those members either way.
    """
    _require_full_mode(user)
    _require_membership(db, user.id, family_id)

    grant = repo.find_grant(db, gift_list.id, family_id)
    if grant is None:
        return

    losing_ids = repo.get_member_ids_losing_access(
        db, gift_list.id, family_id, gift_list.owner_id
    )
    if claims is None and repo.any_claims_by_users(db, gift_list.id, losing_ids):
        raise ConflictError(CLAIMED_MESSAGE)

    repo.delete_grant(db, grant)
    if claims == "release":
        repo.unclaim_for_users(db, gift_list.id, losing_ids)
    repo.delete_collection_items_for_users(db, gift_list.id, losing_ids)


def set_grants_on_create(
    db: Session, gift_list: GiftList, owner: User, family_ids: list[int]
) -> None:
    """Apply the creation-time sharing rule: simple mode shares with every family
    the owner belongs to and ignores the request body; full mode shares with
    exactly the families asked for, each of which the owner must belong to."""
    if owner.simple_mode:
        for family_id in families_repo.family_ids_for_user(db, owner.id):
            repo.create_grant(db, gift_list.id, family_id)
        return
    requested = list(dict.fromkeys(family_ids))
    # Validate every id first: a foreign id partway through must not leave the
    # earlier grants written.
    for family_id in requested:
        _require_membership(db, owner.id, family_id)
    for family_id in requested:
        repo.create_grant(db, gift_list.id, family_id)


def grant_existing_lists_on_join(db: Session, user: User, family_id: int) -> None:
    """On gaining membership, a simple-mode member's existing non-archived lists
    are shared with the new family — they have no in-app way to do it themselves.
    Full-mode members opt in per list instead, so joining never re-shares a list
    its owner deliberately kept private."""
    if not user.simple_mode:
        return
    repo.grant_all_lists_to_family(db, owner_id=user.id, family_id=family_id)
