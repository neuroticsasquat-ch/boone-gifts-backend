from sqlalchemy.orm import Session

from app.claims import repository as claims_repo
from app.families import repository as families_repo
from app.list_occasions import repository as repo
from app.models.gift_list import GiftList
from app.models.occasion import Occasion
from app.models.user import User
from app.occasions import repository as occasions_repo
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

CLAIMED_MESSAGE = "Some gifts on this list are claimed by members of this family."
ARCHIVED_MESSAGE = "This occasion is archived and can no longer be shared to."


def _require_membership(db: Session, user_id: int, family_id: int) -> None:
    if families_repo.get_family_member(db, family_id=family_id, user_id=user_id) is None:
        raise ForbiddenError("Not a member of this family.")


def _load_shareable_occasion(db: Session, occasion_id: int, user: User) -> Occasion:
    """The occasion, having established the caller is a member of its family.

    A missing occasion is a 404 and a foreign one a 403, matching
    `occasions/service.py::_load_for_member` — existence is not concealed, which
    is the repo's established shape for this resource. What membership *does*
    gate is every other fact about the occasion, `is_archived` included, so a
    non-member cannot tell an archived family occasion from an active one.
    """
    occasion = occasions_repo.get_occasion(db, occasion_id)
    if occasion is None:
        raise NotFoundError("Occasion not found.")
    _require_membership(db, user.id, occasion.family_id)
    return occasion


def list_share_targets(db: Session, gift_list: GiftList) -> list[dict]:
    """The sharing control's families half: every family the list's owner belongs
    to, each carrying the occasions it can be shared to and which of them it is
    already shared to.

    An occasion is listed when it is active *or* already holds a share, so a
    share made before archiving still has a name to display — archiving is not
    unsharing (ADR 0002 §5.4). A family with no listed active occasion cannot be
    shared to at all, which is the state the control renders disabled.
    """
    shared = repo.shared_occasion_ids(db, gift_list.id)
    families = repo.get_families_for_user(db, gift_list.owner_id)
    occasions = repo.get_occasions_for_families(db, [f.id for f in families])

    by_family: dict[int, list[dict]] = {family.id: [] for family in families}
    for occasion in occasions:
        is_shared = occasion.id in shared
        if occasion.is_archived and not is_shared:
            continue
        by_family[occasion.family_id].append(
            {
                "id": occasion.id,
                "name": occasion.name,
                "is_archived": occasion.is_archived,
                "shared": is_shared,
            }
        )
    return [
        {"id": family.id, "name": family.name, "occasions": by_family[family.id]}
        for family in families
    ]


def create_share(
    db: Session, gift_list: GiftList, occasion_id: int, user: User
) -> None:
    """Share a list to an occasion. Idempotent.

    Sharing to an archived occasion is refused — archiving blocks new shares,
    and only that (ADR 0002 §5.4).
    """
    occasion = _load_shareable_occasion(db, occasion_id, user)
    if repo.find_share(db, gift_list.id, occasion.id) is not None:
        return
    if occasion.is_archived:
        raise ConflictError(ARCHIVED_MESSAGE)
    repo.create_share(db, gift_list.id, occasion.id)


def revoke_share(
    db: Session,
    gift_list: GiftList,
    occasion_id: int,
    user: User,
    claims: str | None = None,
) -> None:
    """Revoke a list's share on an occasion.

    With no `claims` choice, a family member holding a claim they would lose
    blocks the revoke with a ConflictError and nothing changes. `release`
    unclaims for members who lose every view path; `keep` leaves those claims
    standing. Folder items are deleted for those members either way.

    An archived occasion can still be unshared: archiving only blocks new shares.
    """
    occasion = _load_shareable_occasion(db, occasion_id, user)

    share = repo.find_share(db, gift_list.id, occasion.id)
    if share is None:
        return

    losing_ids = repo.get_member_ids_losing_access(
        db, gift_list.id, occasion, gift_list.owner_id
    )
    if claims is None and claims_repo.any_claims_by_users(db, gift_list.id, losing_ids):
        raise ConflictError(CLAIMED_MESSAGE)

    repo.delete_share(db, share)
    if claims == "release":
        claims_repo.unclaim_for_users(db, gift_list.id, losing_ids)
    repo.delete_folder_items_for_users(db, gift_list.id, losing_ids)


def set_shares_on_create(
    db: Session, gift_list: GiftList, owner: User, occasion_ids: list[int]
) -> None:
    """Apply the creation-time sharing rule: the list is shared to exactly the
    occasions asked for, each on a family the owner belongs to and none of them
    archived. An empty list shares with nobody — there is no auto-grant."""
    requested = list(dict.fromkeys(occasion_ids))
    # Validate every id first: a foreign or archived one partway through must
    # not leave the earlier shares written.
    occasions = []
    for occasion_id in requested:
        occasion = _load_shareable_occasion(db, occasion_id, owner)
        if occasion.is_archived:
            raise ConflictError(ARCHIVED_MESSAGE)
        occasions.append(occasion)
    for occasion in occasions:
        repo.create_share(db, gift_list.id, occasion.id)
