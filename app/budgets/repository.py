"""Every query that touches a budget row.

The rollup's other half — what the caller has actually spent — is counted in
`app/claims/repository.py`, where every claim query lives.
"""
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.budget import Budget


def find_budget(
    db: Session,
    *,
    user_id: int,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> Budget | None:
    """The caller's own budget for one scope, or None if they have not set one.

    Always keyed on `user_id`: there is no query here, and no argument, that
    could return somebody else's budget (`CONTEXT.md` invariant 1).
    """
    scope = (
        Budget.occasion_id == occasion_id
        if occasion_id is not None
        else Budget.folder_id == folder_id
    )
    return db.execute(
        select(Budget).where(Budget.user_id == user_id, scope)
    ).scalar_one_or_none()


def create_budget(
    db: Session,
    *,
    user_id: int,
    amount: Decimal,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> Budget:
    budget = Budget(
        user_id=user_id,
        occasion_id=occasion_id,
        folder_id=folder_id,
        amount=amount,
    )
    db.add(budget)
    db.flush()
    return budget


def update_amount(db: Session, budget: Budget, amount: Decimal) -> Budget:
    budget.amount = amount
    db.flush()
    return budget


def delete_budget(db: Session, budget: Budget) -> None:
    db.delete(budget)
    db.flush()


def delete_budgets_for_folder(db: Session, folder_id: int) -> None:
    """A folder's budget goes with the folder. Nothing else points at it, and
    the foreign key would refuse the delete if it were left behind."""
    db.execute(delete(Budget).where(Budget.folder_id == folder_id))
    db.flush()


def delete_budgets_for_occasions(db: Session, occasion_ids: list[int]) -> None:
    """Every user's budget filed against these occasions.

    Called when a family — and with it its occasions — is deleted. Unlike a
    claim, a budget has nothing to survive for once its occasion is gone: it is
    a target for shopping that can no longer be filed anywhere.
    """
    if not occasion_ids:
        return
    db.execute(delete(Budget).where(Budget.occasion_id.in_(occasion_ids)))
    db.flush()


def delete_budgets_by_user(db: Session, user_id: int) -> None:
    """Every budget this user has set, anywhere."""
    db.execute(delete(Budget).where(Budget.user_id == user_id))
    db.flush()
