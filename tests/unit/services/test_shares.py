from unittest.mock import MagicMock, patch

import pytest

from app.models.collection_item import CollectionItem
from app.models.list_share import ListShare
from app.shares import service
from app.services.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError


REPO = "app.shares.service.repo"
CONN_REPO = "app.shares.service.find_accepted_connection_between"


# --- create_share ---


@patch(f"{REPO}.create_share")
@patch(f"{REPO}.find_share", return_value=None)
@patch(CONN_REPO)
def test_create_share_success(mock_conn, mock_find, mock_create):
    db = MagicMock()
    mock_conn.return_value = MagicMock()  # connection exists
    share = MagicMock(spec=ListShare)
    mock_create.return_value = share

    result = service.create_share(db, list_id=1, user_id=2, current_user_id=10)

    mock_conn.assert_called_once_with(db, 10, 2)
    mock_find.assert_called_once_with(db, 1, 2)
    mock_create.assert_called_once_with(db, 1, 2)
    assert result is share


def test_create_share_self():
    db = MagicMock()
    with pytest.raises(BadRequestError, match="yourself"):
        service.create_share(db, list_id=1, user_id=5, current_user_id=5)


@patch(CONN_REPO, return_value=None)
def test_create_share_not_connected(mock_conn):
    db = MagicMock()
    with pytest.raises(ForbiddenError, match="connected"):
        service.create_share(db, list_id=1, user_id=2, current_user_id=10)


@patch(f"{REPO}.find_share")
@patch(CONN_REPO)
def test_create_share_duplicate(mock_conn, mock_find):
    db = MagicMock()
    mock_conn.return_value = MagicMock()
    mock_find.return_value = MagicMock(spec=ListShare)

    with pytest.raises(ConflictError):
        service.create_share(db, list_id=1, user_id=2, current_user_id=10)


# --- list_shares ---


@patch(f"{REPO}.get_shares_for_list")
def test_list_shares(mock_get):
    db = MagicMock()
    shares = [MagicMock(spec=ListShare), MagicMock(spec=ListShare)]
    mock_get.return_value = shares

    result = service.list_shares(db, list_id=1)

    mock_get.assert_called_once_with(db, 1)
    assert result == shares


# --- delete_share ---


@patch(f"{REPO}.find_collection_items_for_unshare", return_value=[])
@patch(f"{REPO}.delete_share")
@patch(f"{REPO}.find_share")
def test_delete_share_success(mock_find, mock_delete, mock_items):
    db = MagicMock()
    share = MagicMock(spec=ListShare)
    mock_find.return_value = share

    service.delete_share(db, list_id=1, user_id=2)

    mock_find.assert_called_once_with(db, 1, 2)
    mock_delete.assert_called_once_with(db, share)
    mock_items.assert_called_once_with(db, 1, 2)


@patch(f"{REPO}.find_share", return_value=None)
def test_delete_share_not_found(mock_find):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.delete_share(db, list_id=1, user_id=2)


@patch(f"{REPO}.delete_collection_item")
@patch(f"{REPO}.find_collection_items_for_unshare")
@patch(f"{REPO}.delete_share")
@patch(f"{REPO}.find_share")
def test_delete_share_cascades_collection_items(mock_find, mock_delete, mock_items, mock_del_item):
    db = MagicMock()
    share = MagicMock(spec=ListShare)
    mock_find.return_value = share
    item1 = MagicMock(spec=CollectionItem)
    item2 = MagicMock(spec=CollectionItem)
    mock_items.return_value = [item1, item2]

    service.delete_share(db, list_id=1, user_id=2)

    mock_delete.assert_called_once_with(db, share)
    mock_del_item.assert_any_call(db, item1)
    mock_del_item.assert_any_call(db, item2)
    assert mock_del_item.call_count == 2
