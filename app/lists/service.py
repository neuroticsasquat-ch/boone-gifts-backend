from sqlalchemy.orm import Session

from app.account import service as account_service
from app.claims import repository as claims_repo
from app.list_occasions import service as list_occasion_service
from app.lists import repository as repo
from app.models.gift_list import GiftList
from app.models.user import User
from app.schemas.gift_list import (
    GiftListDetailOwner,
    GiftListDetailViewer,
    GiftListRead,
    GiftListViewerRead,
    SharedVia,
    SharedViaFamily,
)
from app.services.exceptions import BadRequestError, ConflictError

RECIPIENT_EXCLUSIVE_MESSAGE = (
    "A list is for an account person or for someone with no account, not both."
)


def _reject_person_with_recipient(
    account_person_id: int | None, recipient_name: str | None
) -> None:
    """§4.1, checked against the *resulting* row. The schema validator catches
    both fields arriving in one payload; only the service can see a partial
    update landing on a row that already carries the other one."""
    if account_person_id is not None and recipient_name is not None:
        raise BadRequestError(RECIPIENT_EXCLUSIVE_MESSAGE)


def create_list(
    db: Session, name: str, description: str | None, owner: User,
    occasion_ids: list[int] | None = None,
    recipient_name: str | None = None,
    account_person_id: int | None = None,
) -> GiftList:
    _reject_person_with_recipient(account_person_id, recipient_name)
    account_service.get_owned_person_id(db, owner.id, account_person_id)
    gift_list = repo.create_list(
        db,
        name=name,
        description=description,
        owner_id=owner.id,
        recipient_name=recipient_name,
        account_person_id=account_person_id,
    )
    list_occasion_service.set_shares_on_create(db, gift_list, owner, occasion_ids or [])
    return gift_list


def to_summary(gift_list: GiftList, user_id: int) -> GiftListRead | GiftListViewerRead:
    """Serialize one list row for one caller.

    The single place that decides whether a row may carry claim state. An owner
    gets `GiftListRead`, which has no `claimed_count` to fill in; anyone else
    gets the viewer schema, which does. Route every list-row response through
    here rather than naming a schema at the endpoint — naming it per endpoint is
    how `claimed_count` came to be returned on owned rows in the first place
    (ADR 0003).
    """
    if gift_list.owner_id == user_id:
        return GiftListRead.model_validate(gift_list)
    return GiftListViewerRead.model_validate(gift_list)


def get_lists(
    db: Session, user_id: int, filter: str | None = None, archived: bool = False
) -> list[GiftListRead | GiftListViewerRead]:
    if filter == "owned":
        rows = repo.get_lists_by_owner(db, user_id, archived=archived)
    elif filter == "shared":
        rows = get_shared_lists(db, user_id, archived=archived)
    else:
        rows = repo.get_all_visible_lists(db, user_id, archived=archived)
    return [to_summary(gift_list, user_id) for gift_list in rows]


def get_shared_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    """Every list someone else has made visible to the caller — directly or through
    an occasion — each annotated with the `shared_via` source that explains it. This
    is the one shared scope; there is no separate family view."""
    rows = repo.get_shared_lists_with_source(db, user_id, archived=archived)
    lists: list[GiftList] = []
    for gift_list, kind, source_id, source_name, family_id, family_name in rows:
        family = (
            SharedViaFamily(id=family_id, name=family_name)
            if family_id is not None
            else None
        )
        gift_list.shared_via = SharedVia(
            kind=kind, id=source_id, name=source_name, family=family
        )
        lists.append(gift_list)
    return lists


def get_list(
    gift_list: GiftList, user_id: int
) -> GiftListDetailOwner | GiftListDetailViewer:
    if gift_list.owner_id == user_id:
        return GiftListDetailOwner.model_validate(gift_list)
    return GiftListDetailViewer.model_validate(gift_list)


def update_list(db: Session, gift_list: GiftList, updates: dict) -> GiftList:
    # `updates` is model_dump(exclude_unset=True), so an absent key means "leave
    # it alone" and an explicit null means "clear it". Resolve both fields to
    # what the row will actually hold before judging the pair.
    resulting_person_id = updates.get("account_person_id", gift_list.account_person_id)
    resulting_recipient = updates.get("recipient_name", gift_list.recipient_name)
    _reject_person_with_recipient(resulting_person_id, resulting_recipient)
    if "account_person_id" in updates:
        account_service.get_owned_person_id(
            db, gift_list.owner_id, updates["account_person_id"]
        )
    return repo.update_list(db, gift_list, updates)


def delete_list(db: Session, gift_list: GiftList) -> None:
    if claims_repo.has_claimed_gifts(db, gift_list.id):
        raise ConflictError(
            "This list has gifts that have been claimed. "
            "Remove claims first or archive the list instead."
        )
    repo.delete_list(db, gift_list)


def get_unseen_share_count(db: Session, user_id: int) -> int:
    return repo.get_unseen_share_count(db, user_id)


def mark_share_seen(db: Session, list_id: int, user_id: int) -> None:
    repo.mark_share_seen(db, list_id, user_id)
