from unittest.mock import MagicMock, patch

import pytest

from app.lists import service
from app.models.gift_list import GiftList
from app.schemas.gift_list import GiftListDetailOwner, GiftListDetailViewer


def _make_gift_list(
    id: int = 1,
    name: str = "My List",
    description: str | None = "A test list",
    owner_id: int = 1,
) -> MagicMock:
    gl = MagicMock(spec=GiftList)
    gl.id = id
    gl.name = name
    gl.description = description
    gl.owner_id = owner_id
    gl.gifts = []
    gl.owner_name = "Test User"
    return gl


REPO = "app.lists.service.repo"


# --- create_list ---


@patch(f"{REPO}.create_list")
def test_create_list(mock_create):
    db = MagicMock()
    expected = _make_gift_list()
    mock_create.return_value = expected

    result = service.create_list(db, name="My List", description="A test list", owner_id=1)

    mock_create.assert_called_once_with(
        db, name="My List", description="A test list", owner_id=1
    )
    assert result == expected


# --- get_lists (filter logic) ---


@patch(f"{REPO}.get_lists_by_owner")
def test_get_lists_owned(mock_get_owned):
    db = MagicMock()
    lists = [_make_gift_list(id=1), _make_gift_list(id=2)]
    mock_get_owned.return_value = lists

    result = service.get_lists(db, user_id=1, filter="owned")

    mock_get_owned.assert_called_once_with(db, 1, archived=False)
    assert len(result) == 2


@patch(f"{REPO}.get_shared_lists")
def test_get_lists_shared(mock_get_shared):
    db = MagicMock()
    lists = [_make_gift_list(id=3, owner_id=2)]
    mock_get_shared.return_value = lists

    result = service.get_lists(db, user_id=1, filter="shared")

    mock_get_shared.assert_called_once_with(db, 1, archived=False)
    assert len(result) == 1


@patch(f"{REPO}.get_all_visible_lists")
def test_get_lists_all(mock_get_all):
    db = MagicMock()
    lists = [_make_gift_list(id=1), _make_gift_list(id=3, owner_id=2)]
    mock_get_all.return_value = lists

    result = service.get_lists(db, user_id=1, filter=None)

    mock_get_all.assert_called_once_with(db, 1, archived=False)
    assert len(result) == 2


# --- get_list (owner vs viewer) ---


@patch("app.lists.service.GiftListDetailOwner.model_validate")
def test_get_list_as_owner(mock_validate):
    gift_list = _make_gift_list(owner_id=5)
    expected = MagicMock(spec=GiftListDetailOwner)
    mock_validate.return_value = expected

    result = service.get_list(gift_list, user_id=5)

    mock_validate.assert_called_once_with(gift_list)
    assert result == expected


@patch("app.lists.service.GiftListDetailViewer.model_validate")
def test_get_list_as_viewer(mock_validate):
    gift_list = _make_gift_list(owner_id=5)
    expected = MagicMock(spec=GiftListDetailViewer)
    mock_validate.return_value = expected

    result = service.get_list(gift_list, user_id=10)

    mock_validate.assert_called_once_with(gift_list)
    assert result == expected


# --- update_list ---


@patch(f"{REPO}.update_list")
def test_update_list(mock_update):
    db = MagicMock()
    gift_list = _make_gift_list()
    updated = _make_gift_list(name="Updated Name")
    mock_update.return_value = updated

    result = service.update_list(db, gift_list, updates={"name": "Updated Name"})

    mock_update.assert_called_once_with(db, gift_list, {"name": "Updated Name"})
    assert result == updated


# --- delete_list ---


@patch(f"{REPO}.delete_list")
def test_delete_list(mock_delete):
    db = MagicMock()
    gift_list = _make_gift_list()

    service.delete_list(db, gift_list)

    mock_delete.assert_called_once_with(db, gift_list)
