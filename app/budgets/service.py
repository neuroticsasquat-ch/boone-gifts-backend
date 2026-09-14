"""Setting, clearing and rolling up one user's own budgets — the overall for a
scope, and the per-giftee split beneath it (NEU-1326).

Deliberately knows nothing about who may read an occasion or a folder. The
scope's own service does that check — `app/occasions/service.py` gates on
family membership, `app/folders/service.py` on ownership — and calls in here
afterwards. Keeping the access rules where the scope lives is also what keeps
the imports acyclic: the occasion and folder services both call this module,
and it calls neither back.

What this module *does* consult is `can_view_list`, the one visibility
predicate (`CONTEXT.md` invariant 2): the giftees it shows are derived from
lists the caller can already view, and routing that through the predicate is
what keeps a term added there from being quietly missed here.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.access import can_view_list
from app.budgets import repository as repo
from app.budgets.giftees import ABSENT, OWNER, PERSON, key_for, parse_key
from app.claims import repository as claims_repo
from app.folders import repository as folders_repo
from app.list_occasions import repository as list_occasions_repo
from app.models.folder import Folder
from app.models.gift_list import GiftList
from app.models.giftee_budget import GifteeBudget
from app.models.user import User
from app.services.exceptions import BadRequestError, NotFoundError

ONE_SCOPE_ONLY = "A budget belongs to one occasion or one folder, never both."
SCOPE_REQUIRED = "A budget must belong to an occasion or a folder."
NO_BUDGET = "No budget is set."
NO_GIFTEE_BUDGET = "No budget is set for this giftee."
MALFORMED_KEY = "Malformed giftee key."
GIFTEE_NOT_IN_SCOPE = "No such giftee in this scope."

ZERO = Decimal("0.00")
_NO_SPEND = {
    "spent": ZERO,
    "bought_count": 0,
    "total_count": 0,
    "unpriced_count": 0,
}


def _require_one_scope(occasion_id: int | None, folder_id: int | None) -> None:
    """Exactly one of the two scopes, in both directions.

    The rule lives here rather than in a check constraint because SQLite cannot
    gain one without `render_as_batch` recreating the table, and because this is
    where the 400 has to be raised anyway. Today's two callers each pass exactly
    one scope, so this guards the *next* caller — which is the one that would
    otherwise write a row belonging to everything or to nothing.
    """
    if occasion_id is not None and folder_id is not None:
        raise BadRequestError(ONE_SCOPE_ONLY)
    if occasion_id is None and folder_id is None:
        raise BadRequestError(SCOPE_REQUIRED)


def _spend(
    db: Session,
    *,
    user_id: int,
    occasion_id: int | None,
    folder_id: int | None,
) -> dict:
    if occasion_id is not None:
        return claims_repo.get_spend_for_occasion(db, occasion_id, user_id)
    return claims_repo.get_spend_for_folder(db, folder_id, user_id)


def _spend_by_giftee(
    db: Session,
    *,
    user_id: int,
    occasion_id: int | None,
    folder_id: int | None,
) -> dict[str, dict]:
    if occasion_id is not None:
        return claims_repo.get_spend_by_giftee_for_occasion(db, occasion_id, user_id)
    return claims_repo.get_spend_by_giftee_for_folder(db, folder_id, user_id)


# ---------------------------------------------------------------------------
# The rollup arithmetic
# ---------------------------------------------------------------------------


def _rollup(
    amount: Decimal | None,
    spend: dict,
    *,
    allocated: Decimal,
    allocation_count: int,
) -> dict:
    """One budget line's numbers (decision 5).

    `target` is what the money line is measured against: the set `amount`, else
    the allocation when at least one giftee budget exists, else nothing.
    `unallocated` only means something against a set overall; `remaining` only
    against a target. Both may go negative — a budget is a target, not a limit,
    and over-allocation is reported, never refused.
    """
    if amount is not None:
        target: Decimal | None = amount
    elif allocation_count:
        target = allocated
    else:
        target = None
    return {
        "amount": amount,
        "spent": spend["spent"],
        "remaining": None if target is None else target - spend["spent"],
        "bought_count": spend["bought_count"],
        "total_count": spend["total_count"],
        "unpriced_count": spend["unpriced_count"],
        "allocated": allocated,
        "unallocated": None if amount is None else amount - allocated,
        "target": target,
        "allocation_count": allocation_count,
    }


def _overall_rollup(
    amount: Decimal | None, spend: dict, giftee_budgets: list[GifteeBudget]
) -> dict:
    """The overall line, with the caller's giftee budgets summed into it.

    Every row in scope counts — including one whose lists have all left the
    scope. It is shown as an empty group, so it counts; nothing that adds to
    `allocated` may be invisible (decision 3).
    """
    return _rollup(
        amount,
        spend,
        allocated=sum((budget.amount for budget in giftee_budgets), ZERO),
        allocation_count=len(giftee_budgets),
    )


def _giftee_rollup(amount: Decimal | None, spend: dict) -> dict:
    """A giftee's line is a leaf: nothing allocates beneath it, so there is
    nothing unallocated either."""
    return {
        **_rollup(amount, spend, allocated=ZERO, allocation_count=0),
        "unallocated": None,
    }


# ---------------------------------------------------------------------------
# The giftee set (decision 3)
# ---------------------------------------------------------------------------


def _visible_lists(
    db: Session,
    *,
    actor: User,
    occasion_id: int | None,
    folder_id: int | None,
) -> list[GiftList]:
    """Source 1: the lists in scope the caller can see — exactly what the Lists
    tab shows — minus the caller's own, which they cannot claim on and so have
    nothing to budget for."""
    if occasion_id is not None:
        candidates = list_occasions_repo.get_lists_shared_to_occasion(db, occasion_id)
    else:
        folder = db.get(Folder, folder_id)
        candidates = folders_repo.get_lists_for_folder(db, folder) if folder else []
    return [
        gift_list
        for gift_list in candidates
        if gift_list.owner_id != actor.id and can_view_list(db, actor, gift_list)
    ]


def _claimed_lists(
    db: Session,
    *,
    user_id: int,
    occasion_id: int | None,
    folder_id: int | None,
) -> list[GiftList]:
    """Source 2: the lists behind the caller's own shopping rows in scope."""
    if occasion_id is not None:
        return claims_repo.get_claimed_lists_for_occasion(db, occasion_id, user_id)
    return claims_repo.get_claimed_lists_for_folder(db, folder_id, user_id)


def _entry_from_list(gift_list: GiftList) -> dict:
    key = key_for(gift_list)
    if gift_list.account_person_id is not None:
        kind, name, keeper = PERSON, gift_list.account_person_name, gift_list.owner_name
    elif gift_list.recipient_name is not None:
        kind, name, keeper = ABSENT, gift_list.recipient_name, gift_list.owner_name
    else:
        kind, name, keeper = OWNER, gift_list.owner_name, None
    return {
        "key": key,
        "kind": kind,
        "name": name,
        "keeper": keeper,
        "owner_id": gift_list.owner_id,
        "account_person_id": gift_list.account_person_id,
        "recipient_name": gift_list.recipient_name,
        "list_count": 0,
    }


def _giftees_from_lists(
    db: Session,
    *,
    actor: User,
    occasion_id: int | None,
    folder_id: int | None,
) -> dict[str, dict]:
    """Sources 1 ∪ 2, keyed by giftee key, each counting the distinct lists
    that resolve to it. This is also the set a giftee write is validated
    against (decision 5): the client can only have got a key from this scope's
    payload, so a miss means the list has since gone."""
    seen: set[int] = set()
    entries: dict[str, dict] = {}
    for gift_list in [
        *_visible_lists(
            db, actor=actor, occasion_id=occasion_id, folder_id=folder_id
        ),
        *_claimed_lists(
            db, user_id=actor.id, occasion_id=occasion_id, folder_id=folder_id
        ),
    ]:
        if gift_list.id in seen:
            continue
        seen.add(gift_list.id)
        entry = entries.setdefault(key_for(gift_list), _entry_from_list(gift_list))
        entry["list_count"] += 1
    return entries


def _add_orphaned_rows(
    db: Session, entries: dict[str, dict], giftee_budgets: list[GifteeBudget]
) -> None:
    """Source 3: a budget row whose lists have all left the scope — or whose
    recipient was renamed — is still a group: empty, labelled, removable.
    Only the triple is in hand, so the owner and the person are resolved by
    id, one query each."""
    orphans = [b for b in giftee_budgets if b.giftee_key not in entries]
    if not orphans:
        return
    owner_names = repo.find_user_names(db, {b.owner_id for b in orphans})
    person_names = repo.find_person_names(
        db, {b.account_person_id for b in orphans if b.account_person_id is not None}
    )
    for budget in orphans:
        keeper = owner_names.get(budget.owner_id, "")
        if budget.account_person_id is not None:
            kind, name = PERSON, person_names.get(budget.account_person_id, "")
        elif budget.recipient_name is not None:
            kind, name = ABSENT, budget.recipient_name
        else:
            kind, name, keeper = OWNER, keeper, None
        entries[budget.giftee_key] = {
            "key": budget.giftee_key,
            "kind": kind,
            "name": name,
            "keeper": keeper,
            "owner_id": budget.owner_id,
            "account_person_id": budget.account_person_id,
            "recipient_name": budget.recipient_name,
            "list_count": 0,
        }


def _giftee_order(entry: dict) -> tuple:
    """Giftees with at least one shopping row first, then the rest; within each
    half by name (case-insensitive), then key. The client renders array order
    and does not re-sort — the rule the occasion index already carries."""
    return (
        entry["budget"]["total_count"] == 0,
        entry["name"].casefold(),
        entry["key"],
    )


def _giftees(
    db: Session,
    *,
    actor: User,
    occasion_id: int | None,
    folder_id: int | None,
    giftee_budgets: list[GifteeBudget],
) -> list[dict]:
    entries = _giftees_from_lists(
        db, actor=actor, occasion_id=occasion_id, folder_id=folder_id
    )
    _add_orphaned_rows(db, entries, giftee_budgets)
    amounts = {budget.giftee_key: budget.amount for budget in giftee_budgets}
    spend = _spend_by_giftee(
        db, user_id=actor.id, occasion_id=occasion_id, folder_id=folder_id
    )
    for key, entry in entries.items():
        entry["budget"] = _giftee_rollup(amounts.get(key), spend.get(key, _NO_SPEND))
    return sorted(entries.values(), key=_giftee_order)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_rollup(
    db: Session,
    *,
    user_id: int,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> dict:
    """The overall budget line: the target, the spend against it, the counts,
    and how much of it the caller has allocated to giftees.

    Returned whether or not a budget exists — the counts describe the caller's
    shopping either way, and a null `amount` is what tells the client to offer
    *set* rather than *edit*. `remaining` is allowed to go negative: a budget is
    a target, not a limit.
    """
    _require_one_scope(occasion_id, folder_id)
    budget = repo.find_budget(
        db, user_id=user_id, occasion_id=occasion_id, folder_id=folder_id
    )
    spend = _spend(
        db, user_id=user_id, occasion_id=occasion_id, folder_id=folder_id
    )
    giftee_budgets = repo.get_giftee_budgets(
        db, user_id=user_id, occasion_id=occasion_id, folder_id=folder_id
    )
    amount: Decimal | None = budget.amount if budget is not None else None
    return _overall_rollup(amount, spend, giftee_budgets)


def get_block(
    db: Session,
    *,
    actor: User,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> dict:
    """The overall rollup and every giftee in scope with theirs — what a
    shopping tab renders above its rows, and what a giftee write answers with.

    The caller is the `User` rather than an id because the giftee set is
    derived through `can_view_list`, which takes one. Every number here is
    still the caller's own: the rollups count the caller's claims, the giftee
    budgets are the caller's rows, and the giftees are derived from lists the
    caller can already view.
    """
    _require_one_scope(occasion_id, folder_id)
    giftee_budgets = repo.get_giftee_budgets(
        db, user_id=actor.id, occasion_id=occasion_id, folder_id=folder_id
    )
    budget = repo.find_budget(
        db, user_id=actor.id, occasion_id=occasion_id, folder_id=folder_id
    )
    spend = _spend(
        db, user_id=actor.id, occasion_id=occasion_id, folder_id=folder_id
    )
    amount: Decimal | None = budget.amount if budget is not None else None
    return {
        "budget": _overall_rollup(amount, spend, giftee_budgets),
        "giftees": _giftees(
            db,
            actor=actor,
            occasion_id=occasion_id,
            folder_id=folder_id,
            giftee_budgets=giftee_budgets,
        ),
    }


# ---------------------------------------------------------------------------
# The overall budget. Nothing here reads or writes `giftee_budgets`.
# ---------------------------------------------------------------------------


def set_budget(
    db: Session,
    *,
    user_id: int,
    amount: Decimal,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> dict:
    """Set or replace the caller's own budget for one scope, and return the
    rollup — the client's budget line is one round trip, not two."""
    _require_one_scope(occasion_id, folder_id)
    budget = repo.find_budget(
        db, user_id=user_id, occasion_id=occasion_id, folder_id=folder_id
    )
    if budget is None:
        repo.create_budget(
            db,
            user_id=user_id,
            amount=amount,
            occasion_id=occasion_id,
            folder_id=folder_id,
        )
    else:
        repo.update_amount(db, budget, amount)
    return get_rollup(
        db, user_id=user_id, occasion_id=occasion_id, folder_id=folder_id
    )


def clear_budget(
    db: Session,
    *,
    user_id: int,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> dict:
    """Remove the caller's own budget, and return the rollup it leaves behind.

    The counts outlive the target — clearing a budget is not unclaiming
    anything — so the client re-renders the same line with no target on it.
    """
    _require_one_scope(occasion_id, folder_id)
    budget = repo.find_budget(
        db, user_id=user_id, occasion_id=occasion_id, folder_id=folder_id
    )
    if budget is None:
        raise NotFoundError(NO_BUDGET)
    repo.delete_budget(db, budget)
    return get_rollup(
        db, user_id=user_id, occasion_id=occasion_id, folder_id=folder_id
    )


# ---------------------------------------------------------------------------
# Giftee budgets. Nothing here reads or writes `budgets`.
# ---------------------------------------------------------------------------


def _parse_key(giftee_key: str):
    try:
        return parse_key(giftee_key)
    except ValueError:
        raise BadRequestError(MALFORMED_KEY)


def set_giftee_budget(
    db: Session,
    *,
    actor: User,
    giftee_key: str,
    amount: Decimal,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> dict:
    """Set or replace the caller's own budget for one giftee, and return the
    whole block — the write moves that giftee's line *and* the overall's
    `allocated` / `target`.

    A malformed key is a 400. A well-formed key must name a giftee the caller
    can currently see in this scope (sources 1 ∪ 2 of decision 3) **or** one
    they already hold a row for: the client can only have got the key from
    this scope's payload, so anything else means the list has since gone, and
    that is a 404. The second clause is what keeps an orphaned group — shown,
    labelled, and carrying an editor — editable as well as removable.

    The stored triple comes from the list the key matched, never from the key:
    a `person` key carries no owner, and the list always has all three.
    """
    _require_one_scope(occasion_id, folder_id)
    _parse_key(giftee_key)
    existing = repo.find_giftee_budget(
        db,
        user_id=actor.id,
        giftee_key=giftee_key,
        occasion_id=occasion_id,
        folder_id=folder_id,
    )
    if existing is not None:
        repo.update_giftee_amount(db, existing, amount)
    else:
        entry = _giftees_from_lists(
            db, actor=actor, occasion_id=occasion_id, folder_id=folder_id
        ).get(giftee_key)
        if entry is None:
            raise NotFoundError(GIFTEE_NOT_IN_SCOPE)
        repo.create_giftee_budget(
            db,
            user_id=actor.id,
            giftee_key=giftee_key,
            owner_id=entry["owner_id"],
            account_person_id=entry["account_person_id"],
            recipient_name=entry["recipient_name"],
            amount=amount,
            occasion_id=occasion_id,
            folder_id=folder_id,
        )
    return get_block(db, actor=actor, occasion_id=occasion_id, folder_id=folder_id)


def clear_giftee_budget(
    db: Session,
    *,
    actor: User,
    giftee_key: str,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> dict:
    """Remove the caller's own budget for one giftee, and return the block it
    leaves behind. 404 when no row exists, as the overall's `DELETE` is.

    Deliberately not gated on the giftee still being in scope: an orphaned row
    is exactly the one the user most needs to be able to remove (decision 3,
    source 3).
    """
    _require_one_scope(occasion_id, folder_id)
    _parse_key(giftee_key)
    budget = repo.find_giftee_budget(
        db,
        user_id=actor.id,
        giftee_key=giftee_key,
        occasion_id=occasion_id,
        folder_id=folder_id,
    )
    if budget is None:
        raise NotFoundError(NO_GIFTEE_BUDGET)
    repo.delete_giftee_budget(db, budget)
    return get_block(db, actor=actor, occasion_id=occasion_id, folder_id=folder_id)
