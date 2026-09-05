from sqlalchemy.orm import Session

from app.list_families import service as list_family_service
from app.lists import repository as repo
from app.models.gift_list import GiftList
from app.models.user import User
from app.schemas.family import FamilyRef
from app.schemas.gift_list import GiftListDetailOwner, GiftListDetailViewer
from app.services.exceptions import ConflictError


def create_list(
    db: Session, name: str, description: str | None, owner: User,
    family_ids: list[int] | None = None,
) -> GiftList:
    gift_list = repo.create_list(
        db, name=name, description=description, owner_id=owner.id
    )
    list_family_service.set_grants_on_create(db, gift_list, owner, family_ids or [])
    return gift_list


def get_lists(db: Session, user_id: int, filter: str | None = None, archived: bool = False) -> list[GiftList]:
    if filter == "owned":
        return repo.get_lists_by_owner(db, user_id, archived=archived)
    elif filter == "shared":
        return repo.get_shared_lists(db, user_id, archived=archived)
    elif filter == "family":
        return get_family_lists(db, user_id, archived=archived)
    else:
        return repo.get_all_visible_lists(db, user_id, archived=archived)


def get_family_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    """Lists owned by the caller's family co-members, each annotated with the
    family/families granting visibility. Co-members sharing multiple families
    collapse to one list carrying all granting families (order preserved)."""
    rows = repo.get_family_visible_lists_with_grants(db, user_id, archived=archived)
    by_id: dict[int, GiftList] = {}
    for gift_list, family_id, family_name in rows:
        existing = by_id.get(gift_list.id)
        if existing is None:
            gift_list.families = []
            by_id[gift_list.id] = gift_list
            existing = gift_list
        existing.families.append(FamilyRef(id=family_id, name=family_name))
    return list(by_id.values())


def get_list(
    gift_list: GiftList, user_id: int
) -> GiftListDetailOwner | GiftListDetailViewer:
    if gift_list.owner_id == user_id:
        return GiftListDetailOwner.model_validate(gift_list)
    return GiftListDetailViewer.model_validate(gift_list)


def update_list(db: Session, gift_list: GiftList, updates: dict) -> GiftList:
    return repo.update_list(db, gift_list, updates)


def delete_list(db: Session, gift_list: GiftList) -> None:
    if repo.has_claimed_gifts(db, gift_list.id):
        raise ConflictError(
            "This list has gifts that have been claimed. "
            "Remove claims first or archive the list instead."
        )
    repo.delete_list(db, gift_list)


def get_unseen_share_count(db: Session, user_id: int) -> int:
    return repo.get_unseen_share_count(db, user_id)


def mark_share_seen(db: Session, list_id: int, user_id: int) -> None:
    repo.mark_share_seen(db, list_id, user_id)
