from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.occasions import service
from app.models.occasion import Occasion
from app.models.occasion_item import OccasionItem
from app.models.gift_list import GiftList
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError


def _make_occasion(
    id: int = 1,
    name: str = "My Occasion",
    description: str | None = None,
    owner_id: int = 1,
) -> MagicMock:
    col = MagicMock(spec=Occasion)
    col.id = id
    col.name = name
    col.description = description
    col.owner_id = owner_id
    col.items = []
    col.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    col.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return col


def _make_gift_list(id: int = 10, owner_id: int = 1) -> MagicMock:
    gl = MagicMock(spec=GiftList)
    gl.id = id
    gl.owner_id = owner_id
    return gl


def _make_occasion_item(
    id: int = 1, occasion_id: int = 1, list_id: int = 10
) -> MagicMock:
    item = MagicMock(spec=OccasionItem)
    item.id = id
    item.occasion_id = occasion_id
    item.list_id = list_id
    return item


REPO = "app.occasions.service.repo"


# --- create_occasion ---


@patch(f"{REPO}.create_occasion")
def test_create_occasion(mock_create):
    db = MagicMock()
    col = _make_occasion()
    mock_create.return_value = col

    result = service.create_occasion(db, name="My Occasion", description=None, owner_id=1)

    mock_create.assert_called_once_with(db, "My Occasion", None, 1)
    assert result.id == 1
    assert result.name == "My Occasion"


# --- list_occasions ---


@patch(f"{REPO}.get_occasions_for_user")
def test_list_occasions(mock_get):
    db = MagicMock()
    col = _make_occasion()
    mock_get.return_value = [col]

    result = service.list_occasions(db, owner_id=1)

    mock_get.assert_called_once_with(db, 1, archived=False)
    assert len(result) == 1
    assert result[0].name == "My Occasion"


# --- get_occasion_detail ---


@patch(f"{REPO}.get_lists_for_occasion")
def test_get_occasion_detail(mock_get_lists):
    db = MagicMock()
    col = _make_occasion(id=1, name="Wishlist", description="Holiday", owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=5)
    mock_get_lists.return_value = [gift_list]

    result = service.get_occasion_detail(db, col)

    mock_get_lists.assert_called_once_with(db, col)
    assert result["id"] == 1
    assert result["name"] == "Wishlist"
    assert result["description"] == "Holiday"
    assert result["owner_id"] == 5
    assert result["lists"] == [gift_list]
    assert result["created_at"] == col.created_at
    assert result["updated_at"] == col.updated_at


# --- update_occasion ---


@patch(f"{REPO}.update_occasion")
def test_update_occasion(mock_update):
    db = MagicMock()
    col = _make_occasion()
    updated = _make_occasion(name="Updated")
    mock_update.return_value = updated

    result = service.update_occasion(db, col, {"name": "Updated"})

    mock_update.assert_called_once_with(db, col, {"name": "Updated"})
    assert result.name == "Updated"


# --- delete_occasion ---


@patch(f"{REPO}.delete_occasion")
def test_delete_occasion(mock_delete):
    db = MagicMock()
    col = _make_occasion()

    service.delete_occasion(db, col)

    mock_delete.assert_called_once_with(db, col)


# --- add_item ---

CAN_VIEW = "app.occasions.service.can_view_list"


@patch(f"{REPO}.create_occasion_item")
@patch(f"{REPO}.find_occasion_item", return_value=None)
@patch(CAN_VIEW, return_value=True)
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_viewable(mock_get_list, mock_can_view, mock_find_item, mock_create_item):
    # Owner / direct-share / shared-family all resolve to can_view_list -> True;
    # discriminating between them is can_view_list's job (tested in app/access),
    # so the service unit test only cares that a viewable list is added.
    db = MagicMock()
    user = SimpleNamespace(id=5)
    col = _make_occasion(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=99)
    mock_get_list.return_value = gift_list

    service.add_item(db, occasion=col, list_id=10, user=user)

    mock_get_list.assert_called_once_with(db, 10)
    mock_can_view.assert_called_once_with(db, user, gift_list)
    mock_find_item.assert_called_once_with(db, 1, 10)
    mock_create_item.assert_called_once_with(db, 1, 10)


@patch(f"{REPO}.create_occasion_item")
@patch(CAN_VIEW, return_value=False)
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_not_viewable(mock_get_list, mock_can_view, mock_create_item):
    db = MagicMock()
    user = SimpleNamespace(id=5)
    col = _make_occasion(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=99)
    mock_get_list.return_value = gift_list

    with pytest.raises(ForbiddenError):
        service.add_item(db, occasion=col, list_id=10, user=user)

    mock_can_view.assert_called_once_with(db, user, gift_list)
    mock_create_item.assert_not_called()


@patch(CAN_VIEW, return_value=True)
@patch(f"{REPO}.find_occasion_item")
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_duplicate(mock_get_list, mock_find_item, mock_can_view):
    db = MagicMock()
    user = SimpleNamespace(id=5)
    col = _make_occasion(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=5)
    mock_get_list.return_value = gift_list
    mock_find_item.return_value = _make_occasion_item()

    with pytest.raises(ConflictError):
        service.add_item(db, occasion=col, list_id=10, user=user)


@patch(f"{REPO}.get_gift_list_by_id", return_value=None)
def test_add_item_list_not_found(mock_get_list):
    # List existence is checked before access, so can_view_list is never reached.
    db = MagicMock()
    user = SimpleNamespace(id=5)
    col = _make_occasion(id=1, owner_id=5)

    with pytest.raises(NotFoundError):
        service.add_item(db, occasion=col, list_id=999, user=user)


# --- remove_item ---


@patch(f"{REPO}.delete_occasion_item")
@patch(f"{REPO}.find_occasion_item")
def test_remove_item(mock_find, mock_delete):
    db = MagicMock()
    col = _make_occasion(id=1)
    item = _make_occasion_item(occasion_id=1, list_id=10)
    mock_find.return_value = item

    service.remove_item(db, occasion=col, list_id=10)

    mock_find.assert_called_once_with(db, 1, 10)
    mock_delete.assert_called_once_with(db, item)


@patch(f"{REPO}.find_occasion_item", return_value=None)
def test_remove_item_not_found(mock_find):
    db = MagicMock()
    col = _make_occasion(id=1)

    with pytest.raises(NotFoundError):
        service.remove_item(db, occasion=col, list_id=999)
