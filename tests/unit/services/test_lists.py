from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.lists import service
from app.models.gift_list import GiftList
from app.schemas.gift_list import (
    GiftListDetailOwner,
    GiftListDetailViewer,
    GiftListRead,
    SharedVia,
)


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
LIST_FAMILY_SVC = "app.lists.service.list_family_service"


# --- create_list ---


@patch(f"{LIST_FAMILY_SVC}.set_grants_on_create")
@patch(f"{REPO}.create_list")
def test_create_list(mock_create, mock_grants):
    db = MagicMock()
    owner = SimpleNamespace(id=1, simple_mode=False)
    expected = _make_gift_list()
    mock_create.return_value = expected

    result = service.create_list(
        db, name="My List", description="A test list", owner=owner, family_ids=[7]
    )

    mock_create.assert_called_once_with(
        db,
        name="My List",
        description="A test list",
        owner_id=1,
        recipient_name=None,
        recipient_has_account=None,
    )
    mock_grants.assert_called_once_with(db, expected, owner, [7])
    assert result == expected


@patch(f"{LIST_FAMILY_SVC}.set_grants_on_create")
@patch(f"{REPO}.create_list")
def test_create_list_without_family_ids_passes_empty_list(mock_create, mock_grants):
    db = MagicMock()
    owner = SimpleNamespace(id=1, simple_mode=False)
    mock_create.return_value = _make_gift_list()

    service.create_list(db, name="My List", description=None, owner=owner)

    mock_grants.assert_called_once_with(db, mock_create.return_value, owner, [])


# --- get_lists (filter logic) ---


@patch(f"{REPO}.get_lists_by_owner")
def test_get_lists_owned(mock_get_owned):
    db = MagicMock()
    lists = [_make_gift_list(id=1), _make_gift_list(id=2)]
    mock_get_owned.return_value = lists

    result = service.get_lists(db, user_id=1, filter="owned")

    mock_get_owned.assert_called_once_with(db, 1, archived=False)
    assert len(result) == 2


@patch(f"{REPO}.get_shared_lists_with_source")
def test_get_lists_shared(mock_get_shared):
    db = MagicMock()
    mock_get_shared.return_value = [(_make_gift_list(id=3, owner_id=2), "user", 2, "Jane")]

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
@patch(f"{REPO}.has_claimed_gifts", return_value=False)
def test_delete_list(mock_has_claims, mock_delete):
    db = MagicMock()
    gift_list = _make_gift_list()

    service.delete_list(db, gift_list)

    mock_has_claims.assert_called_once_with(db, gift_list.id)
    mock_delete.assert_called_once_with(db, gift_list)


@patch(f"{REPO}.has_claimed_gifts", return_value=True)
def test_delete_list_blocked_by_claims(mock_has_claims):
    from app.services.exceptions import ConflictError

    db = MagicMock()
    gift_list = _make_gift_list()

    with pytest.raises(ConflictError, match="claimed"):
        service.delete_list(db, gift_list)


# --- GiftListRead.shared_via annotation ---


def _read_source(shared_via=None):
    """A stand-in for a GiftList ORM instance that GiftListRead.model_validate
    consumes (it reads `.gifts` to compute counts)."""
    obj = SimpleNamespace(
        id=1,
        name="A List",
        description=None,
        owner_id=2,
        owner_name="Owner",
        recipient_name=None,
        recipient_has_account=None,
        is_archived=False,
        gifts=[],
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
    )
    if shared_via is not None:
        obj.shared_via = shared_via
    return obj


def test_gift_list_read_includes_shared_via():
    obj = _read_source(shared_via={"kind": "family", "id": 1, "name": "Boone Family"})
    result = GiftListRead.model_validate(obj)
    assert result.shared_via.kind == "family"
    assert (result.shared_via.id, result.shared_via.name) == (1, "Boone Family")


def test_gift_list_read_shared_via_defaults_none():
    obj = _read_source()  # no shared_via attribute set — an owned list
    result = GiftListRead.model_validate(obj)
    assert result.shared_via is None


# --- get_shared_lists (source annotation) ---


@patch(f"{REPO}.get_shared_lists_with_source")
def test_get_shared_lists_annotates_direct_share(mock_rows):
    db = MagicMock()
    gl = SimpleNamespace(id=10)
    mock_rows.return_value = [(gl, "user", 2, "Jane Boone")]

    result = service.get_shared_lists(db, user_id=5)

    mock_rows.assert_called_once_with(db, 5, archived=False)
    assert result == [gl]
    assert result[0].shared_via == SharedVia(kind="user", id=2, name="Jane Boone")


@patch(f"{REPO}.get_shared_lists_with_source")
def test_get_shared_lists_annotates_family_grant(mock_rows):
    db = MagicMock()
    gl = SimpleNamespace(id=10)
    mock_rows.return_value = [(gl, "family", 1, "Boone Family")]

    result = service.get_shared_lists(db, user_id=5)

    assert result[0].shared_via == SharedVia(kind="family", id=1, name="Boone Family")


@patch(f"{REPO}.get_shared_lists_with_source")
def test_get_shared_lists_preserves_repository_order(mock_rows):
    db = MagicMock()
    gl1, gl2 = SimpleNamespace(id=10), SimpleNamespace(id=20)
    mock_rows.return_value = [(gl1, "user", 2, "Jane"), (gl2, "family", 1, "Boones")]

    result = service.get_shared_lists(db, user_id=5)

    assert [l.id for l in result] == [10, 20]


@patch(f"{REPO}.get_shared_lists_with_source")
def test_get_shared_lists_empty(mock_rows):
    db = MagicMock()
    mock_rows.return_value = []

    assert service.get_shared_lists(db, user_id=5) == []


@patch(f"{REPO}.get_shared_lists_with_source")
def test_get_lists_shared_archived_passthrough(mock_rows):
    db = MagicMock()
    mock_rows.return_value = []

    service.get_lists(db, user_id=5, filter="shared", archived=True)

    mock_rows.assert_called_once_with(db, 5, archived=True)
