from datetime import datetime
from types import SimpleNamespace
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.gifts import service
from app.models.claim import Claim
from app.models.gift import Gift
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)


def _make_gift(id: int = 1, list_id: int = 10, name: str = "Test Gift") -> MagicMock:
    gift = MagicMock(spec=Gift)
    gift.id = id
    gift.list_id = list_id
    gift.name = name
    return gift


def _make_claim(
    gift_id: int = 1,
    user_id: int = 99,
    purchased_at: datetime | None = None,
    amount_paid: Decimal | None = None,
) -> MagicMock:
    claim = MagicMock(spec=Claim)
    claim.gift_id = gift_id
    claim.user_id = user_id
    claim.purchased_at = purchased_at
    claim.amount_paid = amount_paid
    return claim


REPO = "app.gifts.service.repo"
CLAIMS_REPO = "app.gifts.service.claims_repo"
LIST_REPO = "app.gifts.service.list_repo"
RESOLVE = "app.gifts.service.claim_service.resolve_filing"


def _make_non_archived_list():
    gift_list = MagicMock()
    gift_list.is_archived = False
    return gift_list


# --- create_gift ---


@patch(f"{REPO}.create_gift")
def test_create_gift(mock_create):
    db = MagicMock()
    gift = _make_gift()
    mock_create.return_value = gift

    result = service.create_gift(
        db, list_id=10, name="Test Gift", description="Desc", url=None, price=None
    )

    mock_create.assert_called_once_with(db, 10, "Test Gift", "Desc", None, None)
    assert result.id == 1
    assert result.name == "Test Gift"


# --- update_gift ---


@patch(f"{REPO}.update_gift")
@patch(f"{REPO}.get_gift_by_id")
def test_update_gift(mock_get, mock_update):
    db = MagicMock()
    gift = _make_gift(id=1, list_id=10)
    mock_get.return_value = gift
    updated_gift = _make_gift(id=1, list_id=10, name="Updated")
    mock_update.return_value = updated_gift

    result = service.update_gift(db, gift_id=1, list_id=10, updates={"name": "Updated"})

    mock_get.assert_called_once_with(db, 1)
    mock_update.assert_called_once_with(db, gift, {"name": "Updated"})
    assert result.name == "Updated"


@patch(f"{REPO}.get_gift_by_id", return_value=None)
def test_update_gift_not_found(mock_get):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.update_gift(db, gift_id=999, list_id=10, updates={"name": "X"})


@patch(f"{REPO}.get_gift_by_id")
def test_update_gift_wrong_list(mock_get):
    db = MagicMock()
    gift = _make_gift(id=1, list_id=20)  # belongs to list 20, not 10
    mock_get.return_value = gift

    with pytest.raises(NotFoundError):
        service.update_gift(db, gift_id=1, list_id=10, updates={"name": "X"})


# --- delete_gift ---


@patch(f"{REPO}.delete_gift")
@patch(f"{CLAIMS_REPO}.get_claim_for_gift", return_value=None)
@patch(f"{REPO}.get_gift_by_id")
def test_delete_gift(mock_get, mock_claim, mock_delete):
    db = MagicMock()
    gift = _make_gift(id=1, list_id=10)
    mock_get.return_value = gift

    service.delete_gift(db, gift_id=1, list_id=10)

    mock_delete.assert_called_once_with(db, gift)


@patch(f"{CLAIMS_REPO}.get_claim_for_gift")
@patch(f"{REPO}.get_gift_by_id")
def test_delete_gift_claimed(mock_get, mock_claim):
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_claim.return_value = _make_claim(gift_id=1, user_id=99)

    with pytest.raises(ConflictError):
        service.delete_gift(db, gift_id=1, list_id=10)


# --- claim_gift ---


CLAIMER = SimpleNamespace(id=99)


@patch(f"{RESOLVE}", return_value=None)
@patch(f"{CLAIMS_REPO}.get_claim_for_gift", return_value=None)
@patch(f"{LIST_REPO}.get_list_by_id")
@patch(f"{CLAIMS_REPO}.create_claim")
@patch(f"{REPO}.get_gift_by_id")
def test_claim_gift_success(mock_get, mock_claim, mock_get_list, _standing, _resolve):
    db = MagicMock()
    gift = _make_gift(id=1, list_id=10)
    mock_get.return_value = gift
    mock_claim.return_value = _make_claim(gift_id=1, user_id=99)
    mock_get_list.return_value = _make_non_archived_list()

    service.claim_gift(db, gift_id=1, list_id=10, owner_id=5, user=CLAIMER)

    mock_get.assert_called_once_with(db, 1)
    mock_claim.assert_called_once_with(db, 1, 99, None)
    db.refresh.assert_called_once_with(gift)


@patch(f"{REPO}.get_gift_by_id")
def test_claim_gift_by_owner(mock_get):
    db = MagicMock()
    with pytest.raises(ForbiddenError):
        service.claim_gift(
            db, gift_id=1, list_id=10, owner_id=5, user=SimpleNamespace(id=5)
        )

    mock_get.assert_not_called()


@patch(f"{RESOLVE}", return_value=None)
@patch(f"{CLAIMS_REPO}.get_claim_for_gift", return_value=None)
@patch(f"{LIST_REPO}.get_list_by_id")
@patch(f"{CLAIMS_REPO}.create_claim", return_value=None)
@patch(f"{REPO}.get_gift_by_id")
def test_claim_gift_already_claimed(
    mock_get, mock_claim, mock_get_list, _standing, _resolve
):
    """The repository loses the race and says so by returning None."""
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_list.return_value = _make_non_archived_list()

    with pytest.raises(ConflictError):
        service.claim_gift(db, gift_id=1, list_id=10, owner_id=5, user=CLAIMER)

    mock_claim.assert_called_once_with(db, 1, 99, None)


@patch(f"{RESOLVE}")
@patch(f"{CLAIMS_REPO}.get_claim_for_gift")
@patch(f"{LIST_REPO}.get_list_by_id")
@patch(f"{CLAIMS_REPO}.create_claim")
@patch(f"{REPO}.get_gift_by_id")
def test_a_standing_claim_is_409_before_the_filing_is_resolved(
    mock_get, mock_claim, mock_get_list, mock_standing, mock_resolve
):
    """The claim rules that predate filing take precedence, so an already
    claimed gift answers 409 even where the filing would have been ambiguous."""
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_list.return_value = _make_non_archived_list()
    mock_standing.return_value = _make_claim(gift_id=1, user_id=7)

    with pytest.raises(ConflictError):
        service.claim_gift(db, gift_id=1, list_id=10, owner_id=5, user=CLAIMER)

    mock_resolve.assert_not_called()
    mock_claim.assert_not_called()


@patch(f"{RESOLVE}", return_value=3)
@patch(f"{CLAIMS_REPO}.get_claim_for_gift", return_value=None)
@patch(f"{LIST_REPO}.get_list_by_id")
@patch(f"{CLAIMS_REPO}.create_claim")
@patch(f"{REPO}.get_gift_by_id")
def test_the_resolved_filing_is_what_gets_written(
    mock_get, mock_claim, mock_get_list, _standing, mock_resolve
):
    db = MagicMock()
    gift_list = _make_non_archived_list()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_claim.return_value = _make_claim(gift_id=1, user_id=99)
    mock_get_list.return_value = gift_list

    service.claim_gift(
        db, gift_id=1, list_id=10, owner_id=5, user=CLAIMER,
        occasion_id=7, occasion_provided=True,
    )

    mock_resolve.assert_called_once_with(db, gift_list, CLAIMER, 7, True)
    assert mock_claim.call_args.args == (db, 1, 99, 3)


@patch(f"{RESOLVE}", side_effect=BadRequestError("ambiguous_occasion"))
@patch(f"{CLAIMS_REPO}.get_claim_for_gift", return_value=None)
@patch(f"{LIST_REPO}.get_list_by_id")
@patch(f"{CLAIMS_REPO}.create_claim")
@patch(f"{REPO}.get_gift_by_id")
def test_an_ambiguous_filing_writes_no_claim(
    mock_get, mock_claim, mock_get_list, _standing, _resolve
):
    """Resolution happens before the insert, so the 400 leaves nothing behind."""
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_list.return_value = _make_non_archived_list()

    with pytest.raises(BadRequestError):
        service.claim_gift(db, gift_id=1, list_id=10, owner_id=5, user=CLAIMER)

    mock_claim.assert_not_called()


# --- unclaim_gift ---


@patch(f"{LIST_REPO}.get_list_by_id")
@patch(f"{CLAIMS_REPO}.delete_claim")
@patch(f"{CLAIMS_REPO}.get_claim_for_gift")
@patch(f"{REPO}.get_gift_by_id")
def test_unclaim_gift_success(mock_get, mock_get_claim, mock_delete, mock_get_list):
    db = MagicMock()
    gift = _make_gift(id=1, list_id=10)
    claim = _make_claim(gift_id=1, user_id=99)
    mock_get.return_value = gift
    mock_get_claim.return_value = claim
    mock_get_list.return_value = _make_non_archived_list()

    service.unclaim_gift(db, gift_id=1, list_id=10, user_id=99)

    mock_get.assert_called_once_with(db, 1)
    mock_delete.assert_called_once_with(db, claim)
    db.refresh.assert_called_once_with(gift)


@patch(f"{LIST_REPO}.get_list_by_id")
@patch(f"{CLAIMS_REPO}.delete_claim")
@patch(f"{CLAIMS_REPO}.get_claim_for_gift")
@patch(f"{REPO}.get_gift_by_id")
def test_unclaim_gift_not_claimer(mock_get, mock_get_claim, mock_delete, mock_get_list):
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_claim.return_value = _make_claim(gift_id=1, user_id=50)
    mock_get_list.return_value = _make_non_archived_list()

    with pytest.raises(ForbiddenError):
        service.unclaim_gift(db, gift_id=1, list_id=10, user_id=99)

    mock_delete.assert_not_called()


@patch(f"{LIST_REPO}.get_list_by_id")
@patch(f"{CLAIMS_REPO}.delete_claim")
@patch(f"{CLAIMS_REPO}.get_claim_for_gift", return_value=None)
@patch(f"{REPO}.get_gift_by_id")
def test_unclaim_gift_unclaimed(mock_get, mock_get_claim, mock_delete, mock_get_list):
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_list.return_value = _make_non_archived_list()

    with pytest.raises(ForbiddenError):
        service.unclaim_gift(db, gift_id=1, list_id=10, user_id=99)

    mock_delete.assert_not_called()


# --- purchase_gift / unpurchase_gift ---


@patch(f"{CLAIMS_REPO}.update_claim")
@patch(f"{CLAIMS_REPO}.get_claim_for_gift")
@patch(f"{REPO}.get_gift_by_id")
def test_purchase_records_the_amount(mock_get, mock_get_claim, mock_update):
    db = MagicMock()
    claim = _make_claim(gift_id=1, user_id=99)
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_claim.return_value = claim

    service.purchase_gift(
        db, gift_id=1, list_id=10, user_id=99, updates={"amount_paid": Decimal("42.00")}
    )

    updates = mock_update.call_args.args[2]
    assert updates["amount_paid"] == Decimal("42.00")
    assert updates["purchased_at"] is not None


@patch(f"{CLAIMS_REPO}.update_claim")
@patch(f"{CLAIMS_REPO}.get_claim_for_gift")
@patch(f"{REPO}.get_gift_by_id")
def test_purchase_without_an_amount_leaves_it_alone(
    mock_get, mock_get_claim, mock_update
):
    """Skipping the amount is one click, and re-ticking must not wipe what was
    recorded the first time round."""
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_claim.return_value = _make_claim(
        gift_id=1, user_id=99, amount_paid=Decimal("42.00")
    )

    service.purchase_gift(db, gift_id=1, list_id=10, user_id=99, updates={})

    assert "amount_paid" not in mock_update.call_args.args[2]


@patch(f"{CLAIMS_REPO}.update_claim")
@patch(f"{CLAIMS_REPO}.get_claim_for_gift")
@patch(f"{REPO}.get_gift_by_id")
def test_purchase_with_an_explicit_null_clears_the_amount(
    mock_get, mock_get_claim, mock_update
):
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_claim.return_value = _make_claim(
        gift_id=1, user_id=99, amount_paid=Decimal("42.00")
    )

    service.purchase_gift(
        db, gift_id=1, list_id=10, user_id=99, updates={"amount_paid": None}
    )

    assert mock_update.call_args.args[2]["amount_paid"] is None


@patch(f"{CLAIMS_REPO}.get_claim_for_gift")
@patch(f"{REPO}.get_gift_by_id")
def test_purchase_by_a_non_claimer(mock_get, mock_get_claim):
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_claim.return_value = _make_claim(gift_id=1, user_id=50)

    with pytest.raises(ForbiddenError):
        service.purchase_gift(db, gift_id=1, list_id=10, user_id=99, updates={})


@patch(f"{CLAIMS_REPO}.update_claim")
@patch(f"{CLAIMS_REPO}.get_claim_for_gift")
@patch(f"{REPO}.get_gift_by_id")
def test_unpurchase_keeps_the_amount(mock_get, mock_get_claim, mock_update):
    """`amount_paid` survives unticking, so re-ticking does not make the user
    retype what they paid."""
    db = MagicMock()
    mock_get.return_value = _make_gift(id=1, list_id=10)
    mock_get_claim.return_value = _make_claim(
        gift_id=1, user_id=99, purchased_at=datetime(2026, 1, 1)
    )

    service.unpurchase_gift(db, gift_id=1, list_id=10, user_id=99)

    assert mock_update.call_args.args[2] == {"purchased_at": None}
