"""Every query that touches a budget row.

The rollup's other half — what the caller has actually spent — is counted in
`app/claims/repository.py`, where every claim query lives.
"""
from decimal import Decimal

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.account_person import AccountPerson
from app.models.budget import Budget
from app.models.giftee_budget import GifteeBudget
from app.models.user import User


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


# ---------------------------------------------------------------------------
# Giftee budgets (NEU-1326)
# ---------------------------------------------------------------------------


def _giftee_scope(occasion_id: int | None, folder_id: int | None):
    return (
        GifteeBudget.occasion_id == occasion_id
        if occasion_id is not None
        else GifteeBudget.folder_id == folder_id
    )


def get_giftee_budgets(
    db: Session,
    *,
    user_id: int,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> list[GifteeBudget]:
    """The caller's own giftee budgets in one scope. Always keyed on
    `user_id`, like `find_budget` (`CONTEXT.md` invariant 1)."""
    return list(
        db.execute(
            select(GifteeBudget)
            .where(
                GifteeBudget.user_id == user_id,
                _giftee_scope(occasion_id, folder_id),
            )
            .order_by(GifteeBudget.id)
        )
        .scalars()
        .all()
    )


def find_giftee_budget(
    db: Session,
    *,
    user_id: int,
    giftee_key: str,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> GifteeBudget | None:
    return db.execute(
        select(GifteeBudget).where(
            GifteeBudget.user_id == user_id,
            GifteeBudget.giftee_key == giftee_key,
            _giftee_scope(occasion_id, folder_id),
        )
    ).scalar_one_or_none()


def create_giftee_budget(
    db: Session,
    *,
    user_id: int,
    giftee_key: str,
    owner_id: int,
    account_person_id: int | None,
    recipient_name: str | None,
    amount: Decimal,
    occasion_id: int | None = None,
    folder_id: int | None = None,
) -> GifteeBudget:
    budget = GifteeBudget(
        user_id=user_id,
        occasion_id=occasion_id,
        folder_id=folder_id,
        giftee_key=giftee_key,
        owner_id=owner_id,
        account_person_id=account_person_id,
        recipient_name=recipient_name,
        amount=amount,
    )
    db.add(budget)
    db.flush()
    return budget


def update_giftee_amount(
    db: Session, budget: GifteeBudget, amount: Decimal
) -> GifteeBudget:
    budget.amount = amount
    db.flush()
    return budget


def delete_giftee_budget(db: Session, budget: GifteeBudget) -> None:
    db.delete(budget)
    db.flush()


def find_user_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    """Display names for the owners an orphaned giftee budget resolves through
    — a row whose lists have all left the scope has only the triple, and the
    group it still renders as needs a label (decision 3, source 3)."""
    if not user_ids:
        return {}
    return dict(
        db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all()
    )


def find_person_names(db: Session, person_ids: set[int]) -> dict[int, str]:
    """Display names for the account people orphaned giftee budgets are keyed
    on. A person id that no longer resolves cannot happen: deleting the person
    deletes the row (`delete_giftee_budgets_for_people`)."""
    if not person_ids:
        return {}
    return dict(
        db.execute(
            select(AccountPerson.id, AccountPerson.name).where(
                AccountPerson.id.in_(person_ids)
            )
        ).all()
    )


# The four cascades, each beside the overall budget's (decision 7). A recipient
# rename on a list is deliberately not one (ADR 0006), and neither is a list
# leaving the scope: the row stays and shows as an empty group.


def delete_giftee_budgets_for_folder(db: Session, folder_id: int) -> None:
    db.execute(delete(GifteeBudget).where(GifteeBudget.folder_id == folder_id))
    db.flush()


def delete_giftee_budgets_for_occasions(
    db: Session, occasion_ids: list[int]
) -> None:
    if not occasion_ids:
        return
    db.execute(
        delete(GifteeBudget).where(GifteeBudget.occasion_id.in_(occasion_ids))
    )
    db.flush()


def delete_giftee_budgets_by_user(db: Session, user_id: int) -> None:
    """Every giftee budget this user **set**, and every one that resolves
    **through** this user's lists — their lists are going, and with them every
    giftee (themself, their people, their recipients) those lists named."""
    db.execute(
        delete(GifteeBudget).where(
            or_(GifteeBudget.user_id == user_id, GifteeBudget.owner_id == user_id)
        )
    )
    db.flush()


def delete_giftee_budgets_for_people(db: Session, person_ids: list[int]) -> None:
    """Every user's giftee budget keyed on these account people, in every
    scope. Must run before the people rows are deleted; the FK is enforced."""
    if not person_ids:
        return
    db.execute(
        delete(GifteeBudget).where(GifteeBudget.account_person_id.in_(person_ids))
    )
    db.flush()
