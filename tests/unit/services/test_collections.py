from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.collections import service
from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError


def _make_collection(
    id: int = 1,
    name: str = "My Collection",
    description: str | None = None,
    owner_id: int = 1,
) -> MagicMock:
    col = MagicMock(spec=Collection)
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


def _make_collection_item(
    id: int = 1, collection_id: int = 1, list_id: int = 10
) -> MagicMock:
    item = MagicMock(spec=CollectionItem)
    item.id = id
    item.collection_id = collection_id
    item.list_id = list_id
    return item


def _make_share(list_id: int = 10, user_id: int = 1) -> MagicMock:
    share = MagicMock(spec=ListShare)
    share.list_id = list_id
    share.user_id = user_id
    return share


REPO = "app.collections.service.repo"


# --- create_collection ---


@patch(f"{REPO}.create_collection")
def test_create_collection(mock_create):
    db = MagicMock()
    col = _make_collection()
    mock_create.return_value = col

    result = service.create_collection(db, name="My Collection", description=None, owner_id=1)

    mock_create.assert_called_once_with(db, "My Collection", None, 1)
    assert result.id == 1
    assert result.name == "My Collection"


# --- list_collections ---


@patch(f"{REPO}.get_collections_for_user")
def test_list_collections(mock_get):
    db = MagicMock()
    col = _make_collection()
    mock_get.return_value = [col]

    result = service.list_collections(db, owner_id=1)

    mock_get.assert_called_once_with(db, 1)
    assert len(result) == 1
    assert result[0].name == "My Collection"


# --- get_collection_detail ---


@patch(f"{REPO}.get_lists_for_collection")
def test_get_collection_detail(mock_get_lists):
    db = MagicMock()
    col = _make_collection(id=1, name="Wishlist", description="Holiday", owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=5)
    mock_get_lists.return_value = [gift_list]

    result = service.get_collection_detail(db, col)

    mock_get_lists.assert_called_once_with(db, col)
    assert result["id"] == 1
    assert result["name"] == "Wishlist"
    assert result["description"] == "Holiday"
    assert result["owner_id"] == 5
    assert result["lists"] == [gift_list]
    assert result["created_at"] == col.created_at
    assert result["updated_at"] == col.updated_at


# --- update_collection ---


@patch(f"{REPO}.update_collection")
def test_update_collection(mock_update):
    db = MagicMock()
    col = _make_collection()
    updated = _make_collection(name="Updated")
    mock_update.return_value = updated

    result = service.update_collection(db, col, {"name": "Updated"})

    mock_update.assert_called_once_with(db, col, {"name": "Updated"})
    assert result.name == "Updated"


# --- delete_collection ---


@patch(f"{REPO}.delete_collection")
def test_delete_collection(mock_delete):
    db = MagicMock()
    col = _make_collection()

    service.delete_collection(db, col)

    mock_delete.assert_called_once_with(db, col)


# --- add_item ---


@patch(f"{REPO}.create_collection_item")
@patch(f"{REPO}.find_collection_item", return_value=None)
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_owned_list(mock_get_list, mock_find_item, mock_create_item):
    db = MagicMock()
    col = _make_collection(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=5)
    mock_get_list.return_value = gift_list
    item = _make_collection_item()
    mock_create_item.return_value = item

    service.add_item(db, collection=col, list_id=10, user_id=5)

    mock_get_list.assert_called_once_with(db, 10)
    mock_find_item.assert_called_once_with(db, 1, 10)
    mock_create_item.assert_called_once_with(db, 1, 10)


@patch(f"{REPO}.create_collection_item")
@patch(f"{REPO}.find_collection_item", return_value=None)
@patch(f"{REPO}.find_share")
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_shared_list(mock_get_list, mock_find_share, mock_find_item, mock_create_item):
    db = MagicMock()
    col = _make_collection(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=99)  # owned by someone else
    mock_get_list.return_value = gift_list
    mock_find_share.return_value = _make_share(list_id=10, user_id=5)
    item = _make_collection_item()
    mock_create_item.return_value = item

    service.add_item(db, collection=col, list_id=10, user_id=5)

    mock_get_list.assert_called_once_with(db, 10)
    mock_find_share.assert_called_once_with(db, 10, 5)
    mock_find_item.assert_called_once_with(db, 1, 10)
    mock_create_item.assert_called_once_with(db, 1, 10)


@patch(f"{REPO}.find_share", return_value=None)
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_no_access(mock_get_list, mock_find_share):
    db = MagicMock()
    col = _make_collection(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=99)
    mock_get_list.return_value = gift_list

    with pytest.raises(ForbiddenError):
        service.add_item(db, collection=col, list_id=10, user_id=5)


@patch(f"{REPO}.find_collection_item")
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_duplicate(mock_get_list, mock_find_item):
    db = MagicMock()
    col = _make_collection(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=5)
    mock_get_list.return_value = gift_list
    mock_find_item.return_value = _make_collection_item()

    with pytest.raises(ConflictError):
        service.add_item(db, collection=col, list_id=10, user_id=5)


@patch(f"{REPO}.get_gift_list_by_id", return_value=None)
def test_add_item_list_not_found(mock_get_list):
    db = MagicMock()
    col = _make_collection(id=1, owner_id=5)

    with pytest.raises(NotFoundError):
        service.add_item(db, collection=col, list_id=999, user_id=5)


# --- remove_item ---


@patch(f"{REPO}.delete_collection_item")
@patch(f"{REPO}.find_collection_item")
def test_remove_item(mock_find, mock_delete):
    db = MagicMock()
    col = _make_collection(id=1)
    item = _make_collection_item(collection_id=1, list_id=10)
    mock_find.return_value = item

    service.remove_item(db, collection=col, list_id=10)

    mock_find.assert_called_once_with(db, 1, 10)
    mock_delete.assert_called_once_with(db, item)


@patch(f"{REPO}.find_collection_item", return_value=None)
def test_remove_item_not_found(mock_find):
    db = MagicMock()
    col = _make_collection(id=1)

    with pytest.raises(NotFoundError):
        service.remove_item(db, collection=col, list_id=999)
