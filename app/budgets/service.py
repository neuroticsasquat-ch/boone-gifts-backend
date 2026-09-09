"""Setting, clearing and rolling up one user's own budget.

Deliberately knows nothing about who may read an occasion or a folder. The
scope's own service does that check — `app/occasions/service.py` gates on
family membership, `app/folders/service.py` on ownership — and calls in here
afterwards. Keeping the access rules where the scope lives is also what keeps
the imports acyclic: the occasion and folder services both call this module,
and it calls neither back.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.budgets import repository as repo
from app.claims import repository as claims_repo
from app.services.exceptions import BadRequestError, NotFoundError

ONE_SCOPE_ONLY = "A budget belongs to one occasion or one folder, never both."
SCOPE_REQUIRED = "A budget must belong to an occasion or a folder."
NO_BUDGET = "No budget is set."


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


def get_rollup(
    db: Session,
    *,
    user_id: int,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> dict:
    """The budget line: the target, the spend against it, and the counts.

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
    amount: Decimal | None = budget.amount if budget is not None else None
    return {
        "amount": amount,
        "spent": spend["spent"],
        "remaining": None if amount is None else amount - spend["spent"],
        "bought_count": spend["bought_count"],
        "total_count": spend["total_count"],
        "unpriced_count": spend["unpriced_count"],
    }


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
