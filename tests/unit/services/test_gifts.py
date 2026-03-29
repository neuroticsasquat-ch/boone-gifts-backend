from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.gifts import service
from app.models.gift import Gift
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError


def _make_gift(
    id: int = 1,
    list_id: int = 10,
    name: str = "Test Gift",
    claimed_by_id: int | None = None,
    claimed_at: datetime | None = None,
) -> MagicMock:
    gift = MagicMock(spec=Gift)
    gift.id = id
    gift.list_id = list_id
    gift.name = name
    gift.claimed_by_id = claimed_by_id
    gift.claimed_at = claimed_at
    return gift


REPO = "app.gifts.service.repo"


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
@patch(f"{REPO}.get_gift_by_id")
def test_delete_gift(mock_get, mock_delete):
    db = MagicMock()
    gift = _make_gift(id=1, list_id=10, claimed_by_id=None)
    mock_get.return_value = gift

    service.delete_gift(db, gift_id=1, list_id=10)

    mock_delete.assert_called_once_with(db, gift)


@patch(f"{REPO}.get_gift_by_id")
def test_delete_gift_claimed(mock_get):
    db = MagicMock()
    gift = _make_gift(id=1, list_id=10, claimed_by_id=99)
    mock_get.return_value = gift

    with pytest.raises(ConflictError):
        service.delete_gift(db, gift_id=1, list_id=10)


# --- claim_gift ---


@patch(f"{REPO}.get_gift_by_id")
def test_claim_gift_success(mock_get):
    db = MagicMock()
    gift = _make_gift(id=1, list_id=10, claimed_by_id=None)
    mock_get.return_value = gift

    result = service.claim_gift(db, gift_id=1, list_id=10, owner_id=5, user_id=99)

    assert result.claimed_by_id == 99
    assert result.claimed_at is not None


@patch(f"{REPO}.get_gift_by_id")
def test_claim_gift_by_owner(mock_get):
    db = MagicMock()
    # Owner should not be able to claim their own gift
    with pytest.raises(ForbiddenError):
        service.claim_gift(db, gift_id=1, list_id=10, owner_id=5, user_id=5)

    # repo should never be called
    mock_get.assert_not_called()


@patch(f"{REPO}.get_gift_by_id")
def test_claim_gift_already_claimed(mock_get):
    db = MagicMock()
    gift = _make_gift(
        id=1,
        list_id=10,
        claimed_by_id=50,
        claimed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    mock_get.return_value = gift

    with pytest.raises(ConflictError):
        service.claim_gift(db, gift_id=1, list_id=10, owner_id=5, user_id=99)


# --- unclaim_gift ---


@patch(f"{REPO}.get_gift_by_id")
def test_unclaim_gift_success(mock_get):
    db = MagicMock()
    gift = _make_gift(
        id=1,
        list_id=10,
        claimed_by_id=99,
        claimed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    mock_get.return_value = gift

    result = service.unclaim_gift(db, gift_id=1, list_id=10, user_id=99)

    assert result.claimed_by_id is None
    assert result.claimed_at is None


@patch(f"{REPO}.get_gift_by_id")
def test_unclaim_gift_not_claimer(mock_get):
    db = MagicMock()
    gift = _make_gift(
        id=1,
        list_id=10,
        claimed_by_id=50,
        claimed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    mock_get.return_value = gift

    with pytest.raises(ForbiddenError):
        service.unclaim_gift(db, gift_id=1, list_id=10, user_id=99)
