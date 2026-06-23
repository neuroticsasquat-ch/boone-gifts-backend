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


# --- GiftListRead.families annotation ---


def _read_source(families=None):
    """A stand-in for a GiftList ORM instance that GiftListRead.model_validate
    consumes (it reads `.gifts` to compute counts)."""
    obj = SimpleNamespace(
        id=1,
        name="A List",
        description=None,
        owner_id=2,
        owner_name="Owner",
        is_archived=False,
        gifts=[],
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
    )
    if families is not None:
        obj.families = families
    return obj


def test_gift_list_read_includes_families():
    obj = _read_source(
        families=[{"id": 1, "name": "Boone Family"}, {"id": 2, "name": "Holidays"}]
    )
    result = GiftListRead.model_validate(obj)
    assert [(f.id, f.name) for f in result.families] == [
        (1, "Boone Family"),
        (2, "Holidays"),
    ]


def test_gift_list_read_families_defaults_empty():
    obj = _read_source()  # no families attribute set
    result = GiftListRead.model_validate(obj)
    assert result.families == []


# --- get_family_lists (grouping + annotation) ---


@patch(f"{REPO}.get_family_visible_lists_with_grants")
def test_get_family_lists_single_family(mock_grants):
    db = MagicMock()
    gl = SimpleNamespace(id=10)
    mock_grants.return_value = [(gl, 1, "Boone Family")]

    result = service.get_family_lists(db, user_id=5)

    mock_grants.assert_called_once_with(db, 5, archived=False)
    assert len(result) == 1
    assert result[0].id == 10
    assert [(f.id, f.name) for f in result[0].families] == [(1, "Boone Family")]


@patch(f"{REPO}.get_family_visible_lists_with_grants")
def test_get_family_lists_dedups_multi_family(mock_grants):
    db = MagicMock()
    # Two rows for the same list id (co-member shares two families) -> one list.
    gl_a = SimpleNamespace(id=10)
    gl_b = SimpleNamespace(id=10)
    mock_grants.return_value = [(gl_a, 1, "Boone Family"), (gl_b, 2, "Holidays")]

    result = service.get_family_lists(db, user_id=5)

    assert len(result) == 1
    assert result[0] is gl_a  # first occurrence wins
    assert [f.name for f in result[0].families] == ["Boone Family", "Holidays"]


@patch(f"{REPO}.get_family_visible_lists_with_grants")
def test_get_family_lists_multiple_owners_preserves_order(mock_grants):
    db = MagicMock()
    gl1 = SimpleNamespace(id=10)
    gl2 = SimpleNamespace(id=20)
    mock_grants.return_value = [(gl1, 1, "F1"), (gl2, 1, "F1")]

    result = service.get_family_lists(db, user_id=5)

    assert [l.id for l in result] == [10, 20]
    assert [f.name for f in result[0].families] == ["F1"]
    assert [f.name for f in result[1].families] == ["F1"]


@patch(f"{REPO}.get_family_visible_lists_with_grants")
def test_get_family_lists_empty(mock_grants):
    db = MagicMock()
    mock_grants.return_value = []

    result = service.get_family_lists(db, user_id=5)

    assert result == []


@patch(f"{REPO}.get_family_visible_lists_with_grants")
def test_get_lists_family_filter_dispatches(mock_grants):
    db = MagicMock()
    gl = SimpleNamespace(id=10)
    mock_grants.return_value = [(gl, 1, "F1")]

    result = service.get_lists(db, user_id=5, filter="family")

    mock_grants.assert_called_once_with(db, 5, archived=False)
    assert len(result) == 1


@patch(f"{REPO}.get_family_visible_lists_with_grants")
def test_get_lists_family_archived_passthrough(mock_grants):
    db = MagicMock()
    mock_grants.return_value = []

    service.get_lists(db, user_id=5, filter="family", archived=True)

    mock_grants.assert_called_once_with(db, 5, archived=True)
