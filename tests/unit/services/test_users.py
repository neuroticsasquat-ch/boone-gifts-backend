from unittest.mock import MagicMock

import pytest

from app.models.user import User
from app.services.exceptions import NotFoundError
from app.users import service


def _make_user(
    id: int,
    name: str = "Test",
    email: str = "test@test.com",
    role: str = "member",
    is_active: bool = True,
) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = id
    user.name = name
    user.email = email
    user.role = role
    user.is_active = is_active
    return user


REPO = "app.users.service.repo"


# --- list_users ---


@pytest.fixture
def db():
    return MagicMock()


from unittest.mock import patch


@patch(f"{REPO}.get_all_users")
def test_list_users(mock_get_all, db):
    users = [_make_user(1, "Alice"), _make_user(2, "Bob")]
    mock_get_all.return_value = users

    result = service.list_users(db)

    mock_get_all.assert_called_once_with(db)
    assert result == users
    assert len(result) == 2


# --- get_user ---


@patch(f"{REPO}.find_user_by_id")
def test_get_user_found(mock_find, db):
    user = _make_user(1, "Alice", "alice@test.com")
    mock_find.return_value = user

    result = service.get_user(db, user_id=1)

    mock_find.assert_called_once_with(db, 1)
    assert result.id == 1
    assert result.name == "Alice"


@patch(f"{REPO}.find_user_by_id", return_value=None)
def test_get_user_not_found(mock_find, db):
    with pytest.raises(NotFoundError):
        service.get_user(db, user_id=999)

    mock_find.assert_called_once_with(db, 999)


# --- update_user ---


@patch(f"{REPO}.update_user")
@patch(f"{REPO}.find_user_by_id")
def test_update_user(mock_find, mock_update, db):
    user = _make_user(1, "Alice", "alice@test.com")
    mock_find.return_value = user
    updated_user = _make_user(1, "Alice Updated", "alice@test.com")
    mock_update.return_value = updated_user

    updates = {"name": "Alice Updated"}
    result = service.update_user(db, user_id=1, updates=updates)

    mock_find.assert_called_once_with(db, 1)
    mock_update.assert_called_once_with(db, user, updates)
    assert result.name == "Alice Updated"


@patch(f"{REPO}.find_user_by_id", return_value=None)
def test_update_user_not_found(mock_find, db):
    with pytest.raises(NotFoundError):
        service.update_user(db, user_id=999, updates={"name": "New"})

    mock_find.assert_called_once_with(db, 999)


# --- delete_user ---


@patch(f"{REPO}.delete_user")
@patch(f"{REPO}.find_user_by_id")
def test_delete_user(mock_find, mock_delete, db):
    user = _make_user(1, "Alice")
    mock_find.return_value = user

    service.delete_user(db, user_id=1)

    mock_find.assert_called_once_with(db, 1)
    mock_delete.assert_called_once_with(db, user)


@patch(f"{REPO}.find_user_by_id", return_value=None)
def test_delete_user_not_found(mock_find, db):
    with pytest.raises(NotFoundError):
        service.delete_user(db, user_id=999)

    mock_find.assert_called_once_with(db, 999)
