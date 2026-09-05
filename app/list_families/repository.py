from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_family_share import ListFamilyShare
from app.models.list_share import ListShare


def find_grant(db: Session, list_id: int, family_id: int) -> ListFamilyShare | None:
    return db.execute(
        select(ListFamilyShare).where(
            ListFamilyShare.list_id == list_id,
            ListFamilyShare.family_id == family_id,
        )
    ).scalar_one_or_none()


def create_grant(db: Session, list_id: int, family_id: int) -> ListFamilyShare:
    grant = ListFamilyShare(list_id=list_id, family_id=family_id)
    db.add(grant)
    db.flush()
    return grant


def delete_grant(db: Session, grant: ListFamilyShare) -> None:
    db.delete(grant)
    db.flush()


def granted_family_ids(db: Session, list_id: int) -> set[int]:
    return set(
        db.execute(
            select(ListFamilyShare.family_id).where(ListFamilyShare.list_id == list_id)
        ).scalars()
    )


def list_granted_to_any_family_of(db: Session, list_id: int, user_id: int) -> bool:
    """Whether the list is granted to at least one family `user_id` belongs to."""
    return bool(
        db.execute(
            select(
                exists().where(
                    ListFamilyShare.list_id == list_id,
                    FamilyMember.family_id == ListFamilyShare.family_id,
                    FamilyMember.user_id == user_id,
                )
            )
        ).scalar()
    )


def get_families_for_user(db: Session, user_id: int) -> list[Family]:
    family_ids = select(FamilyMember.family_id).where(FamilyMember.user_id == user_id)
    return list(
        db.execute(
            select(Family).where(Family.id.in_(family_ids)).order_by(Family.name)
        )
        .scalars()
        .all()
    )


def delete_grants_for_list(db: Session, list_id: int) -> None:
    db.execute(delete(ListFamilyShare).where(ListFamilyShare.list_id == list_id))


def delete_grants_for_family(db: Session, family_id: int) -> None:
    db.execute(delete(ListFamilyShare).where(ListFamilyShare.family_id == family_id))


def delete_grants_for_owner_in_family(db: Session, owner_id: int, family_id: int) -> None:
    """Drop the departing member's grants on one family, preserving the invariant
    that a grant implies the owner is still a member of that family."""
    owned_list_ids = select(GiftList.id).where(GiftList.owner_id == owner_id)
    db.execute(
        delete(ListFamilyShare).where(
            ListFamilyShare.family_id == family_id,
            ListFamilyShare.list_id.in_(owned_list_ids),
        )
    )


def grant_all_lists_to_family(db: Session, owner_id: int, family_id: int) -> None:
    """Grant every non-archived list owned by `owner_id` to `family_id`, skipping
    any grant that already exists. Used for the simple-mode auto-grant on join."""
    list_ids = set(
        db.execute(
            select(GiftList.id).where(
                GiftList.owner_id == owner_id,
                GiftList.is_archived == False,  # noqa: E712 - SQL expression, not a bool test
            )
        ).scalars()
    )
    already = set(
        db.execute(
            select(ListFamilyShare.list_id).where(
                ListFamilyShare.family_id == family_id,
                ListFamilyShare.list_id.in_(list_ids),
            )
        ).scalars()
    )
    for list_id in sorted(list_ids - already):
        db.add(ListFamilyShare(list_id=list_id, family_id=family_id))
    db.flush()


def get_member_ids_losing_access(
    db: Session, list_id: int, family_id: int, owner_id: int
) -> list[int]:
    """Members of `family_id` who would lose all view paths to `list_id` once its
    grant on that family is revoked: not the owner, no ListShare, and no other
    still-granting family they belong to."""
    member_ids = list(
        db.execute(
            select(FamilyMember.user_id).where(FamilyMember.family_id == family_id)
        ).scalars()
    )
    shared_user_ids = set(
        db.execute(
            select(ListShare.user_id).where(ListShare.list_id == list_id)
        ).scalars()
    )
    other_granting_ids = granted_family_ids(db, list_id) - {family_id}

    losing = []
    for user_id in member_ids:
        if user_id == owner_id or user_id in shared_user_ids:
            continue
        if other_granting_ids and _in_any_family(db, user_id, other_granting_ids):
            continue
        losing.append(user_id)
    return losing


def _in_any_family(db: Session, user_id: int, family_ids: set[int]) -> bool:
    return bool(
        db.execute(
            select(
                exists().where(
                    FamilyMember.user_id == user_id,
                    FamilyMember.family_id.in_(family_ids),
                )
            )
        ).scalar()
    )


def any_claims_by_users(db: Session, list_id: int, user_ids: list[int]) -> bool:
    if not user_ids:
        return False
    return (
        db.execute(
            select(Gift.id)
            .where(Gift.list_id == list_id, Gift.claimed_by_id.in_(user_ids))
            .limit(1)
        ).first()
        is not None
    )


def unclaim_for_users(db: Session, list_id: int, user_ids: list[int]) -> None:
    if not user_ids:
        return
    gifts = db.execute(
        select(Gift).where(Gift.list_id == list_id, Gift.claimed_by_id.in_(user_ids))
    ).scalars().all()
    for gift in gifts:
        gift.claimed_by_id = None
        gift.claimed_at = None
        gift.purchased_at = None
    db.flush()


def delete_collection_items_for_users(
    db: Session, list_id: int, user_ids: list[int]
) -> None:
    if not user_ids:
        return
    collection_ids = select(Collection.id).where(Collection.owner_id.in_(user_ids))
    db.execute(
        delete(CollectionItem).where(
            CollectionItem.list_id == list_id,
            CollectionItem.collection_id.in_(collection_ids),
        )
    )
    db.flush()
