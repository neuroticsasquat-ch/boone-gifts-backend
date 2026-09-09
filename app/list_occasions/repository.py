from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.gift_list import GiftList
from app.models.list_occasion_share import ListOccasionShare
from app.models.list_share import ListShare
from app.models.occasion import Occasion


def find_share(db: Session, list_id: int, occasion_id: int) -> ListOccasionShare | None:
    return db.execute(
        select(ListOccasionShare).where(
            ListOccasionShare.list_id == list_id,
            ListOccasionShare.occasion_id == occasion_id,
        )
    ).scalar_one_or_none()


def create_share(db: Session, list_id: int, occasion_id: int) -> ListOccasionShare:
    share = ListOccasionShare(list_id=list_id, occasion_id=occasion_id)
    db.add(share)
    db.flush()
    return share


def delete_share(db: Session, share: ListOccasionShare) -> None:
    db.delete(share)
    db.flush()


def shared_occasion_ids(db: Session, list_id: int) -> set[int]:
    return set(
        db.execute(
            select(ListOccasionShare.occasion_id).where(
                ListOccasionShare.list_id == list_id
            )
        ).scalars()
    )


def list_shared_to_any_occasion_of(db: Session, list_id: int, user_id: int) -> bool:
    """Whether the list is shared to at least one occasion of a family `user_id`
    belongs to. Deliberately blind to `is_archived`: archiving an occasion blocks
    new shares and nothing else, so it never withdraws visibility (ADR 0002)."""
    return bool(
        db.execute(
            select(
                exists().where(
                    ListOccasionShare.list_id == list_id,
                    Occasion.id == ListOccasionShare.occasion_id,
                    FamilyMember.family_id == Occasion.family_id,
                    FamilyMember.user_id == user_id,
                )
            )
        ).scalar()
    )


def get_lists_shared_to_occasion(db: Session, occasion_id: int) -> list[GiftList]:
    list_ids = select(ListOccasionShare.list_id).where(
        ListOccasionShare.occasion_id == occasion_id
    )
    return list(
        db.execute(
            select(GiftList)
            .where(GiftList.id.in_(list_ids))
            .order_by(GiftList.updated_at.desc(), GiftList.id.desc())
        )
        .scalars()
        .all()
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


def get_occasions_for_families(
    db: Session, family_ids: list[int]
) -> list[Occasion]:
    if not family_ids:
        return []
    return list(
        db.execute(
            select(Occasion)
            .where(Occasion.family_id.in_(family_ids))
            .order_by(Occasion.family_id, Occasion.id)
        )
        .scalars()
        .all()
    )


def delete_shares_for_family(db: Session, family_id: int) -> None:
    occasion_ids = select(Occasion.id).where(Occasion.family_id == family_id)
    db.execute(
        delete(ListOccasionShare).where(
            ListOccasionShare.occasion_id.in_(occasion_ids)
        )
    )


def delete_shares_for_owner_in_family(
    db: Session, owner_id: int, family_id: int
) -> None:
    """Drop the departing member's shares on one family's occasions, preserving
    the invariant that a share implies the owner is still a member of the
    occasion's family."""
    owned_list_ids = select(GiftList.id).where(GiftList.owner_id == owner_id)
    occasion_ids = select(Occasion.id).where(Occasion.family_id == family_id)
    db.execute(
        delete(ListOccasionShare).where(
            ListOccasionShare.occasion_id.in_(occasion_ids),
            ListOccasionShare.list_id.in_(owned_list_ids),
        )
    )


def families_still_sharing(
    db: Session, list_id: int, excluding_occasion_id: int
) -> set[int]:
    """The families reached by the list's *other* occasion shares. The occasion
    being revoked may well have a sibling on the same family, in which case that
    family stays here and nobody in it loses access."""
    return set(
        db.execute(
            select(Occasion.family_id)
            .join(ListOccasionShare, ListOccasionShare.occasion_id == Occasion.id)
            .where(
                ListOccasionShare.list_id == list_id,
                ListOccasionShare.occasion_id != excluding_occasion_id,
            )
        ).scalars()
    )


def get_member_ids_losing_access(
    db: Session, list_id: int, occasion: Occasion, owner_id: int
) -> list[int]:
    """Members of the occasion's family who would lose every view path to
    `list_id` once its share on that occasion is revoked: not the owner, no
    ListShare, and no other still-sharing family they belong to."""
    member_ids = list(
        db.execute(
            select(FamilyMember.user_id).where(
                FamilyMember.family_id == occasion.family_id
            )
        ).scalars()
    )
    shared_user_ids = set(
        db.execute(
            select(ListShare.user_id).where(ListShare.list_id == list_id)
        ).scalars()
    )
    other_family_ids = families_still_sharing(db, list_id, occasion.id)

    losing = []
    for user_id in member_ids:
        if user_id == owner_id or user_id in shared_user_ids:
            continue
        if other_family_ids and _in_any_family(db, user_id, other_family_ids):
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


def delete_folder_items_for_users(
    db: Session, list_id: int, user_ids: list[int]
) -> None:
    if not user_ids:
        return
    folder_ids = select(Folder.id).where(Folder.owner_id.in_(user_ids))
    db.execute(
        delete(FolderItem).where(
            FolderItem.list_id == list_id,
            FolderItem.folder_id.in_(folder_ids),
        )
    )
    db.flush()


def get_shared_occasions_for_member(
    db: Session, list_id: int, user_id: int
) -> list[tuple[Occasion, Family]]:
    """Every occasion the list is shared to whose family `user_id` belongs to,
    each with that family — the raw material for both claim-filing sets
    (NEU-1269 §2).

    Archived occasions are included: narrowing to active is a decision the
    caller makes for `suggested` alone, and `allowed` has to stay wide or a
    misfiled late claim could never be moved back.

    One query per list, not per gift.
    """
    return list(
        db.execute(
            select(Occasion, Family)
            .join(ListOccasionShare, ListOccasionShare.occasion_id == Occasion.id)
            .join(Family, Family.id == Occasion.family_id)
            .join(
                FamilyMember,
                (FamilyMember.family_id == Occasion.family_id)
                & (FamilyMember.user_id == user_id),
            )
            .where(ListOccasionShare.list_id == list_id)
            .order_by(Family.name, Occasion.name, Occasion.id)
        ).all()
    )
