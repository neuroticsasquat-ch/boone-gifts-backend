"""The budget service: the scope rule, and the arithmetic of a budget line.

The mutual-exclusion rule is enforced here rather than by a check constraint
(SQLite cannot gain one without `render_as_batch` recreating the table), so it
is tested here in both directions — both scopes and neither.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.budgets import service
from app.services.exceptions import BadRequestError, NotFoundError

REPO = "app.budgets.service.repo"
CLAIMS_REPO = "app.budgets.service.claims_repo"


def _spend(spent="0", bought=0, total=0, unpriced=0) -> dict:
    return {
        "spent": Decimal(spent),
        "bought_count": bought,
        "total_count": total,
        "unpriced_count": unpriced,
    }


def _budget(amount: str) -> MagicMock:
    budget = MagicMock()
    budget.amount = Decimal(amount)
    return budget


# ---------------------------------------------------------------------------
# Exactly one scope, in both directions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda db: service.get_rollup(db, user_id=1, occasion_id=2, folder_id=3),
        lambda db: service.set_budget(
            db, user_id=1, amount=Decimal("10"), occasion_id=2, folder_id=3
        ),
        lambda db: service.clear_budget(db, user_id=1, occasion_id=2, folder_id=3),
    ],
)
def test_both_scopes_is_refused(call):
    """A budget filed against an occasion *and* a folder would be counted twice
    and cleared once. Nothing writes one."""
    with patch(REPO) as repo, patch(CLAIMS_REPO):
        with pytest.raises(BadRequestError, match="never both"):
            call(MagicMock())
    repo.create_budget.assert_not_called()


@pytest.mark.parametrize(
    "call",
    [
        lambda db: service.get_rollup(db, user_id=1),
        lambda db: service.set_budget(db, user_id=1, amount=Decimal("10")),
        lambda db: service.clear_budget(db, user_id=1),
    ],
)
def test_neither_scope_is_refused(call):
    """A budget belonging to nothing is unreachable from either tab, and would
    silently take the place of the real one on the next write."""
    with patch(REPO) as repo, patch(CLAIMS_REPO):
        with pytest.raises(BadRequestError, match="must belong"):
            call(MagicMock())
    repo.create_budget.assert_not_called()


# ---------------------------------------------------------------------------
# The rollup
# ---------------------------------------------------------------------------


def test_rollup_reports_no_target_when_no_budget_is_set():
    """The counts still describe the caller's shopping, and a null amount is
    what tells the client to offer *set* rather than *edit*."""
    db = MagicMock()
    with patch(REPO) as repo, patch(CLAIMS_REPO) as claims_repo:
        repo.find_budget.return_value = None
        claims_repo.get_spend_for_occasion.return_value = _spend(
            spent="18.00", bought=1, total=3
        )

        rollup = service.get_rollup(db, user_id=1, occasion_id=2)

    assert rollup == {
        "amount": None,
        "spent": Decimal("18.00"),
        "remaining": None,
        "bought_count": 1,
        "total_count": 3,
        "unpriced_count": 0,
    }


def test_rollup_subtracts_the_spend_from_the_target():
    db = MagicMock()
    with patch(REPO) as repo, patch(CLAIMS_REPO) as claims_repo:
        repo.find_budget.return_value = _budget("200.00")
        claims_repo.get_spend_for_occasion.return_value = _spend(
            spent="142.00", bought=3, total=7, unpriced=2
        )

        rollup = service.get_rollup(db, user_id=1, occasion_id=2)

    assert rollup["amount"] == Decimal("200.00")
    assert rollup["spent"] == Decimal("142.00")
    assert rollup["remaining"] == Decimal("58.00")
    assert rollup["bought_count"] == 3
    assert rollup["total_count"] == 7
    assert rollup["unpriced_count"] == 2


def test_rollup_lets_remaining_go_negative():
    """A budget is a target, not a limit — hiding an overspend is the one thing
    a budget line must not do."""
    db = MagicMock()
    with patch(REPO) as repo, patch(CLAIMS_REPO) as claims_repo:
        repo.find_budget.return_value = _budget("50.00")
        claims_repo.get_spend_for_occasion.return_value = _spend(
            spent="80.00", bought=2, total=2
        )

        rollup = service.get_rollup(db, user_id=1, occasion_id=2)

    assert rollup["remaining"] == Decimal("-30.00")


def test_rollup_counts_a_folder_through_the_folder_query():
    db = MagicMock()
    with patch(REPO) as repo, patch(CLAIMS_REPO) as claims_repo:
        repo.find_budget.return_value = None
        claims_repo.get_spend_for_folder.return_value = _spend()

        service.get_rollup(db, user_id=1, folder_id=9)

    claims_repo.get_spend_for_folder.assert_called_once_with(db, 9, 1)
    claims_repo.get_spend_for_occasion.assert_not_called()


# ---------------------------------------------------------------------------
# Writing and clearing
# ---------------------------------------------------------------------------


def test_set_budget_creates_when_none_exists():
    db = MagicMock()
    with patch(REPO) as repo, patch(CLAIMS_REPO) as claims_repo:
        repo.find_budget.side_effect = [None, _budget("200.00")]
        claims_repo.get_spend_for_occasion.return_value = _spend()

        rollup = service.set_budget(
            db, user_id=1, amount=Decimal("200.00"), occasion_id=2
        )

    repo.create_budget.assert_called_once_with(
        db, user_id=1, amount=Decimal("200.00"), occasion_id=2, folder_id=None
    )
    repo.update_amount.assert_not_called()
    assert rollup["amount"] == Decimal("200.00")


def test_set_budget_replaces_the_existing_target():
    """The write is a whole replace, not a delta — one budget per scope, and
    the second `PUT` moves it rather than adding another."""
    db = MagicMock()
    existing = _budget("200.00")
    with patch(REPO) as repo, patch(CLAIMS_REPO) as claims_repo:
        repo.find_budget.return_value = existing
        claims_repo.get_spend_for_occasion.return_value = _spend()

        service.set_budget(db, user_id=1, amount=Decimal("250.00"), occasion_id=2)

    repo.update_amount.assert_called_once_with(db, existing, Decimal("250.00"))
    repo.create_budget.assert_not_called()


def test_clear_budget_deletes_and_returns_the_counts_it_leaves():
    """Clearing a target is not unclaiming anything, so the tally survives it."""
    db = MagicMock()
    existing = _budget("200.00")
    with patch(REPO) as repo, patch(CLAIMS_REPO) as claims_repo:
        repo.find_budget.side_effect = [existing, None]
        claims_repo.get_spend_for_occasion.return_value = _spend(
            spent="18.00", bought=1, total=3
        )

        rollup = service.clear_budget(db, user_id=1, occasion_id=2)

    repo.delete_budget.assert_called_once_with(db, existing)
    assert rollup["amount"] is None
    assert rollup["remaining"] is None
    assert rollup["spent"] == Decimal("18.00")
    assert rollup["total_count"] == 3


def test_clear_budget_raises_not_found_when_none_is_set():
    db = MagicMock()
    with patch(REPO) as repo, patch(CLAIMS_REPO):
        repo.find_budget.return_value = None

        with pytest.raises(NotFoundError):
            service.clear_budget(db, user_id=1, occasion_id=2)

    repo.delete_budget.assert_not_called()
