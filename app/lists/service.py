from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.account import service as account_service
from app.claims import repository as claims_repo
from app.claims import service as claim_service
from app.list_occasions import service as list_occasion_service
from app.lists import repository as repo
from app.models.gift_list import GiftList
from app.models.user import User
from app.schemas.gift_list import (
    GiftListDetailOwner,
    GiftListDetailViewer,
    GiftListRead,
    GiftListViewerRead,
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
    gets `GiftListRead`, which has no `claimed_count` or
    `my_unpurchased_claim_count` to fill in; anyone else gets the viewer schema,
    which does. Route every list-row response through here rather than naming a
    schema at the endpoint — naming it per endpoint is how `claimed_count` came
    to be returned on owned rows in the first place (ADR 0003).

    The viewer schema is told who is asking, because
    `my_unpurchased_claim_count` counts *this* caller's own unbought claims
    rather than the row's total. It refuses to validate without that, so a
    caller who reaches it another way fails loudly instead of serving everyone
    an empty badge.
    """
    if gift_list.owner_id == user_id:
        return GiftListRead.model_validate(gift_list)
    return GiftListViewerRead.model_validate(
        gift_list, context={"viewer_id": user_id}
    )


def to_summaries(
    db: Session, lists: Sequence[GiftList], viewer_id: int
) -> list[GiftListRead | GiftListViewerRead]:
    """Serialize list rows for one caller, each carrying its share routes.

    The seam the list-row surfaces go through. `to_summary` decides which schema
    a row gets and has no `Session` to ask about routes with; this adds the one
    batched query that answers for the whole page, so a surface that calls it
    cannot ship empty `shared_via` arrays by forgetting a step. Four do —
    `/lists`, folder detail, occasion detail, a connection's lists — and a fifth
    inherits the routes by calling this rather than `to_summary`.

    It is a convention, not an enforced one: `UserRead.lists` (admin-only
    `/users`) serializes the ORM relationship straight through `GiftListRead`
    and so always answers `[]`. That is the right answer there — the
    relationship is the user's *own* lists, which have no routes by definition —
    but it is not this function's doing, and a surface that skips this seam gets
    no help from it.

    One query for the routes however many rows there are: the mapping is fetched
    once and read per row — and none at all for a page the caller owns outright.
    """
    # Both arms of the union exclude the caller's own lists, so a route query
    # about one is a question whose answer is already known. Asking only about
    # the rest means `?filter=owned`, where every row is owned, makes no route
    # query at all rather than one guaranteed to come back empty — and it is the
    # same predicate the SQL already applies, not a second one to keep in step.
    foreign_ids = [
        gift_list.id for gift_list in lists if gift_list.owner_id != viewer_id
    ]
    routes = repo.get_share_routes(db, viewer_id, foreign_ids)
    for gift_list in lists:
        # Absent from the mapping means no route: a row the caller owns, or one
        # they reached some way this endpoint does not report. Either way an
        # empty array, never null.
        gift_list.shared_via = routes.get(gift_list.id, [])
    return [to_summary(gift_list, viewer_id) for gift_list in lists]


def get_lists(
    db: Session, user_id: int, filter: str | None = None, archived: bool = False
) -> list[GiftListRead | GiftListViewerRead]:
    if filter == "owned":
        rows = repo.get_lists_by_owner(db, user_id, archived=archived)
    elif filter == "shared":
        rows = get_shared_lists(db, user_id, archived=archived)
    else:
        rows = repo.get_all_visible_lists(db, user_id, archived=archived)
    return to_summaries(db, rows, user_id)


def get_shared_lists(db: Session, user_id: int, archived: bool = False) -> list[GiftList]:
    """Every list someone else has made visible to the caller — directly or
    through an occasion. This is the one shared scope; there is no separate
    family view.

    The scope is the set of lists the caller has a route to, so it is taken from
    `get_share_routes`' keys rather than restated as a second union that could
    drift from it. The rows themselves are then loaded filtered by `archived`,
    which the routes say nothing about: an archived list still has routes, it
    just belongs on the other page.

    `to_summaries` attaches the routes to whichever rows survive that filter, so
    this returns them bare. That does mean the union runs twice on this path —
    once here for the scope, once there for the rows that survived `archived`.
    The alternative is threading the mapping fetched here through `get_lists`
    into `to_summaries`, which buys one query back at the cost of a parameter
    every other caller has to pass correctly, and of a second way for routes to
    reach a row. Both queries are constant in the number of rows, so the cost
    does not grow with the page.
    """
    routes = repo.get_share_routes(db, user_id)
    return repo.get_lists_by_ids(db, list(routes), archived=archived)


def get_list(
    db: Session, gift_list: GiftList, user: User
) -> GiftListDetailOwner | GiftListDetailViewer:
    """Serialize one list's detail for one caller.

    The owner's schema never learns what a claim could be filed under: those two
    sets are derived from the *viewer's* memberships, and an owner sees no claim
    state at all. Same reasoning as `to_summary` — one place decides, so the
    choice cannot be made wrongly per endpoint (ADR 0003).
    """
    if gift_list.owner_id == user.id:
        return GiftListDetailOwner.model_validate(gift_list)
    detail = GiftListDetailViewer.model_validate(gift_list)
    # One query per list detail, not per gift: filing candidates are a property
    # of the list's shares, not of any gift on it.
    allowed, suggested = claim_service.occasion_sets(db, gift_list, user)
    detail.claim_candidates = suggested
    detail.claim_options = allowed
    return detail


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
