from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.connection import Connection
from app.models.user import User
from app.connections import service
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)


def _make_user(
    id: int,
    name: str = "Test",
    email: str = "test@test.com",
    is_active: bool = True,
) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = id
    user.name = name
    user.email = email
    user.is_active = is_active
    return user


def _make_connection(
    id: int,
    requester_id: int,
    addressee_id: int,
    status: str = "pending",
    accepted_at: datetime | None = None,
) -> MagicMock:
    conn = MagicMock(spec=Connection)
    conn.id = id
    conn.requester_id = requester_id
    conn.addressee_id = addressee_id
    conn.status = status
    conn.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn.accepted_at = accepted_at
    return conn


REPO = "app.connections.service.repo"
SEND_EMAIL = "app.connections.service.send_email"


# --- create_connection ---


@patch(SEND_EMAIL)
@patch(f"{REPO}.create_connection")
@patch(f"{REPO}.find_connection_between", return_value=None)
@patch(f"{REPO}.find_user_by_id")
def test_create_connection_by_user_id(mock_find_user, mock_find_conn, mock_create, mock_send):
    db = MagicMock()
    target = _make_user(2, "Alice", "alice@test.com")
    requester = _make_user(1, "Requester", "req@test.com")
    # calls: resolve target (id=2), email requester (id=1), build_response other (id=2)
    mock_find_user.side_effect = [target, requester, target]
    connection = _make_connection(1, 1, 2)
    mock_create.return_value = connection

    result = service.create_connection(db, requester_id=1, target_user_id=2)

    mock_find_user.assert_any_call(db, 2)
    mock_find_conn.assert_called_once_with(db, 1, 2)
    mock_create.assert_called_once_with(db, 1, 2)
    mock_send.assert_called_once()
    assert result["id"] == 1
    assert result["user"]["name"] == "Alice"


@patch(SEND_EMAIL)
@patch(f"{REPO}.create_connection")
@patch(f"{REPO}.find_connection_between", return_value=None)
@patch(f"{REPO}.find_user_by_email")
@patch(f"{REPO}.find_user_by_id")
def test_create_connection_by_email(mock_find_id, mock_find_email, mock_find_conn, mock_create, mock_send):
    db = MagicMock()
    target = _make_user(3, "Bob", "bob@test.com")
    requester = _make_user(1, "Requester", "req@test.com")
    mock_find_email.return_value = target
    # calls: email requester (id=1), build_response other (id=3)
    mock_find_id.side_effect = [requester, target]
    connection = _make_connection(2, 1, 3)
    mock_create.return_value = connection

    result = service.create_connection(db, requester_id=1, target_email="bob@test.com")

    mock_find_email.assert_called_once_with(db, "bob@test.com")
    mock_send.assert_called_once()
    assert result["user"]["email"] == "bob@test.com"


@patch(SEND_EMAIL)
@patch(f"{REPO}.create_connection")
@patch(f"{REPO}.find_connection_between", return_value=None)
@patch(f"{REPO}.find_user_by_id")
def test_create_connection_no_email_when_inactive(mock_find_user, mock_find_conn, mock_create, mock_send):
    db = MagicMock()
    target = _make_user(2, "Alice", "alice@test.com", is_active=False)
    requester = _make_user(1, "Requester", "req@test.com")
    mock_find_user.side_effect = [target, requester, target]
    connection = _make_connection(1, 1, 2)
    mock_create.return_value = connection

    service.create_connection(db, requester_id=1, target_user_id=2)

    mock_send.assert_not_called()


@patch(f"{REPO}.find_user_by_id", return_value=None)
def test_create_connection_user_not_found(mock_find):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.create_connection(db, requester_id=1, target_user_id=999)


@patch(f"{REPO}.find_user_by_id")
def test_create_connection_self(mock_find):
    db = MagicMock()
    mock_find.return_value = _make_user(1)

    with pytest.raises(BadRequestError, match="yourself"):
        service.create_connection(db, requester_id=1, target_user_id=1)


@patch(f"{REPO}.find_connection_between")
@patch(f"{REPO}.find_user_by_id")
def test_create_connection_duplicate(mock_find_user, mock_find_conn):
    db = MagicMock()
    mock_find_user.return_value = _make_user(2)
    mock_find_conn.return_value = _make_connection(1, 1, 2)

    with pytest.raises(ConflictError):
        service.create_connection(db, requester_id=1, target_user_id=2)


# --- accept_connection ---


@patch(f"{REPO}.find_user_by_id")
@patch(f"{REPO}.update_connection_accepted")
@patch(f"{REPO}.find_connection_by_id")
def test_accept_connection_success(mock_find, mock_update, mock_find_user):
    db = MagicMock()
    conn = _make_connection(1, 10, 20, status="pending")
    mock_find.return_value = conn
    mock_update.return_value = conn
    mock_find_user.return_value = _make_user(10, "Requester", "req@test.com")

    result = service.accept_connection(db, connection_id=1, user_id=20)

    mock_update.assert_called_once_with(db, conn)
    assert result["id"] == 1


@patch(f"{REPO}.find_connection_by_id", return_value=None)
def test_accept_connection_not_found(mock_find):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.accept_connection(db, connection_id=999, user_id=1)


@patch(f"{REPO}.find_connection_by_id")
def test_accept_connection_not_addressee(mock_find):
    db = MagicMock()
    mock_find.return_value = _make_connection(1, 10, 20)

    with pytest.raises(ForbiddenError):
        service.accept_connection(db, connection_id=1, user_id=10)


@patch(f"{REPO}.find_connection_by_id")
def test_accept_connection_already_accepted(mock_find):
    db = MagicMock()
    mock_find.return_value = _make_connection(1, 10, 20, status="accepted")

    with pytest.raises(ConflictError):
        service.accept_connection(db, connection_id=1, user_id=20)


# --- delete_connection ---


@patch(f"{REPO}.delete_connection")
@patch(f"{REPO}.find_connection_by_id")
def test_delete_pending_connection(mock_find, mock_delete):
    db = MagicMock()
    conn = _make_connection(1, 10, 20, status="pending")
    mock_find.return_value = conn

    service.delete_connection(db, connection_id=1, user_id=10)

    mock_delete.assert_called_once_with(db, conn)


@patch(f"{REPO}.delete_collection_items_between")
@patch(f"{REPO}.delete_shares_between")
@patch(f"{REPO}.unclaim_gifts_between")
@patch(f"{REPO}.delete_connection")
@patch(f"{REPO}.find_connection_by_id")
def test_delete_accepted_connection_cascades(
    mock_find, mock_delete, mock_unclaim, mock_shares, mock_items
):
    db = MagicMock()
    conn = _make_connection(1, 10, 20, status="accepted")
    mock_find.return_value = conn

    service.delete_connection(db, connection_id=1, user_id=10)

    mock_unclaim.assert_called_once_with(db, 10, 20)
    mock_shares.assert_called_once_with(db, 10, 20)
    mock_items.assert_called_once_with(db, 10, 20)
    mock_delete.assert_called_once_with(db, conn)


@patch(f"{REPO}.find_connection_by_id", return_value=None)
def test_delete_connection_not_found(mock_find):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.delete_connection(db, connection_id=999, user_id=1)


@patch(f"{REPO}.find_connection_by_id")
def test_delete_connection_not_party(mock_find):
    db = MagicMock()
    mock_find.return_value = _make_connection(1, 10, 20)

    with pytest.raises(ForbiddenError):
        service.delete_connection(db, connection_id=1, user_id=99)


# --- list_connections ---


@patch(f"{REPO}.find_user_by_id")
@patch(f"{REPO}.get_accepted_connections")
def test_list_connections(mock_get, mock_find_user):
    db = MagicMock()
    conn = _make_connection(1, 5, 10, status="accepted")
    mock_get.return_value = [conn]
    mock_find_user.return_value = _make_user(10, "Other", "other@test.com")

    result = service.list_connections(db, user_id=5)

    assert len(result) == 1
    assert result[0]["user"]["name"] == "Other"


@patch(f"{REPO}.get_accepted_connections", return_value=[])
def test_list_connections_empty(mock_get):
    db = MagicMock()
    result = service.list_connections(db, user_id=5)
    assert result == []


# --- list_requests ---


@patch(f"{REPO}.find_user_by_id")
@patch(f"{REPO}.get_pending_requests")
def test_list_requests(mock_get, mock_find_user):
    db = MagicMock()
    conn = _make_connection(1, 10, 5, status="pending")
    mock_get.return_value = [conn]
    mock_find_user.return_value = _make_user(10, "Sender", "sender@test.com")

    result = service.list_requests(db, user_id=5)

    assert len(result) == 1
    assert result[0]["user"]["name"] == "Sender"
    assert result[0]["status"] == "pending"


@patch(f"{REPO}.get_pending_requests", return_value=[])
def test_list_requests_empty(mock_get):
    db = MagicMock()
    result = service.list_requests(db, user_id=5)
    assert result == []


# --- cascade_disconnect ---


@patch(f"{REPO}.delete_collection_items_between")
@patch(f"{REPO}.delete_shares_between")
@patch(f"{REPO}.unclaim_gifts_between")
def test_cascade_disconnect(mock_unclaim, mock_shares, mock_items):
    db = MagicMock()
    service.cascade_disconnect(db, 10, 20)

    mock_unclaim.assert_called_once_with(db, 10, 20)
    mock_shares.assert_called_once_with(db, 10, 20)
    mock_items.assert_called_once_with(db, 10, 20)


# --- build_connection_response ---


@patch(f"{REPO}.find_user_by_id")
def test_build_response_as_requester(mock_find):
    db = MagicMock()
    conn = _make_connection(1, 5, 10, status="accepted")
    mock_find.return_value = _make_user(10, "Addressee", "addr@test.com")

    result = service.build_connection_response(db, conn, current_user_id=5)

    mock_find.assert_called_once_with(db, 10)
    assert result["user"]["name"] == "Addressee"


@patch(f"{REPO}.find_user_by_id")
def test_build_response_as_addressee(mock_find):
    db = MagicMock()
    conn = _make_connection(1, 5, 10, status="accepted")
    mock_find.return_value = _make_user(5, "Requester", "req@test.com")

    result = service.build_connection_response(db, conn, current_user_id=10)

    mock_find.assert_called_once_with(db, 5)
    assert result["user"]["name"] == "Requester"
