from sqlalchemy.orm import Session

from app.list_families import service as list_family_service
from app.lists import repository as repo
from app.models.gift_list import GiftList
from app.models.user import User
from app.schemas.gift_list import (
    GiftListDetailOwner,
    GiftListDetailViewer,
    SharedVia,
)
from app.services.exceptions import ConflictError


def create_list(
    db: Session, name: str, description: str | None, owner: User,
    family_ids: list[int] | None = None,
    recipient_name: str | None = None,
    recipient_has_account: bool | None = None,
) -> GiftList:
    gift_list = repo.create_list(
        db,
        name=name,
        description=description,
        owner_id=owner.id,
        recipient_name=recipient_name,
        recipient_has_account=recipient_has_account,
    )
    list_family_service.set_grants_on_create(db, gift_list, owner, family_ids or [])
    return gift_list


def get_lists(db: Session, user_id: int, filter: str | None = None, archived: bool = False) -> list[GiftList]:
    if filter == "owned":
        return repo.get_lists_by_owner(db, user_id, archived=archived)
    elif filter == "shared":
        return get_shared_lists(db, user_id, archived=archived)
    else:
        return repo.get_all_visible_lists(db, user_id, archived=archived)


def get_shared_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    """Every list someone else has made visible to the caller — directly or through
    a family — each annotated with the `shared_via` source that explains it. This is
    the one shared scope; there is no separate family view."""
    rows = repo.get_shared_lists_with_source(db, user_id, archived=archived)
    lists: list[GiftList] = []
    for gift_list, kind, source_id, source_name in rows:
        gift_list.shared_via = SharedVia(kind=kind, id=source_id, name=source_name)
        lists.append(gift_list)
    return lists


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
