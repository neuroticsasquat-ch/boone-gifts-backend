from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.folders import service
from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.gift_list import GiftList
from app.schemas.gift_list import GiftListRead, GiftListViewerRead
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError


def _make_folder(
    id: int = 1,
    name: str = "My Folder",
    description: str | None = None,
    owner_id: int = 1,
) -> MagicMock:
    col = MagicMock(spec=Folder)
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
    gl.name = f"List {id}"
    gl.description = None
    gl.owner_name = "Test User"
    gl.recipient_name = None
    gl.account_person_id = None
    gl.account_person_name = None
    gl.is_archived = False
    gl.gifts = []
    gl.gift_count = 0
    gl.shared_via = None
    gl.created_at = datetime(2026, 1, 1)
    gl.updated_at = datetime(2026, 1, 1)
    return gl


def _make_folder_item(
    id: int = 1, folder_id: int = 1, list_id: int = 10
) -> MagicMock:
    item = MagicMock(spec=FolderItem)
    item.id = id
    item.folder_id = folder_id
    item.list_id = list_id
    return item


REPO = "app.folders.service.repo"


# --- create_folder ---


@patch(f"{REPO}.create_folder")
def test_create_folder(mock_create):
    db = MagicMock()
    col = _make_folder()
    mock_create.return_value = col

    result = service.create_folder(db, name="My Folder", description=None, owner_id=1)

    mock_create.assert_called_once_with(db, "My Folder", None, 1)
    assert result.id == 1
    assert result.name == "My Folder"


# --- list_folders ---


@patch(f"{REPO}.get_folders_for_user")
def test_list_folders(mock_get):
    db = MagicMock()
    col = _make_folder()
    mock_get.return_value = [col]

    result = service.list_folders(db, owner_id=1)

    mock_get.assert_called_once_with(db, 1, archived=False)
    assert len(result) == 1
    assert result[0].name == "My Folder"


# --- get_folder_detail ---


@patch(f"{REPO}.get_lists_for_folder")
def test_get_folder_detail(mock_get_lists):
    db = MagicMock()
    col = _make_folder(id=1, name="Wishlist", description="Holiday", owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=5)
    mock_get_lists.return_value = [gift_list]

    result = service.get_folder_detail(db, col, viewer_id=5)

    mock_get_lists.assert_called_once_with(db, col)
    assert result["id"] == 1
    assert result["name"] == "Wishlist"
    assert result["description"] == "Holiday"
    assert result["owner_id"] == 5
    assert [row.id for row in result["lists"]] == [gift_list.id]
    assert result["created_at"] == col.created_at
    assert result["updated_at"] == col.updated_at


@patch(f"{REPO}.get_lists_for_folder")
def test_get_folder_detail_serializes_each_row_for_the_folders_owner(mock_get_lists):
    """A folder holds lists its owner mostly does not own, so the row schema is
    chosen per list: their own carry no claim state, everyone else's do."""
    db = MagicMock()
    col = _make_folder(id=1, owner_id=5)
    own = _make_gift_list(id=10, owner_id=5)
    someone_elses = _make_gift_list(id=11, owner_id=6)
    mock_get_lists.return_value = [own, someone_elses]

    rows = service.get_folder_detail(db, col, viewer_id=5)["lists"]

    assert type(rows[0]) is GiftListRead
    assert type(rows[1]) is GiftListViewerRead


# --- update_folder ---


@patch(f"{REPO}.update_folder")
def test_update_folder(mock_update):
    db = MagicMock()
    col = _make_folder()
    updated = _make_folder(name="Updated")
    mock_update.return_value = updated

    result = service.update_folder(db, col, {"name": "Updated"})

    mock_update.assert_called_once_with(db, col, {"name": "Updated"})
    assert result.name == "Updated"


# --- delete_folder ---


@patch(f"{REPO}.delete_folder")
def test_delete_folder(mock_delete):
    db = MagicMock()
    col = _make_folder()

    service.delete_folder(db, col)

    mock_delete.assert_called_once_with(db, col)


# --- add_item ---

CAN_VIEW = "app.folders.service.can_view_list"


@patch(f"{REPO}.create_folder_item")
@patch(f"{REPO}.find_folder_item", return_value=None)
@patch(CAN_VIEW, return_value=True)
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_viewable(mock_get_list, mock_can_view, mock_find_item, mock_create_item):
    # Owner / direct-share / shared-family all resolve to can_view_list -> True;
    # discriminating between them is can_view_list's job (tested in app/access),
    # so the service unit test only cares that a viewable list is added.
    db = MagicMock()
    user = SimpleNamespace(id=5)
    col = _make_folder(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=99)
    mock_get_list.return_value = gift_list

    service.add_item(db, folder=col, list_id=10, user=user)

    mock_get_list.assert_called_once_with(db, 10)
    mock_can_view.assert_called_once_with(db, user, gift_list)
    mock_find_item.assert_called_once_with(db, 1, 10)
    mock_create_item.assert_called_once_with(db, 1, 10)


@patch(f"{REPO}.create_folder_item")
@patch(CAN_VIEW, return_value=False)
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_not_viewable(mock_get_list, mock_can_view, mock_create_item):
    db = MagicMock()
    user = SimpleNamespace(id=5)
    col = _make_folder(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=99)
    mock_get_list.return_value = gift_list

    with pytest.raises(ForbiddenError):
        service.add_item(db, folder=col, list_id=10, user=user)

    mock_can_view.assert_called_once_with(db, user, gift_list)
    mock_create_item.assert_not_called()


@patch(CAN_VIEW, return_value=True)
@patch(f"{REPO}.find_folder_item")
@patch(f"{REPO}.get_gift_list_by_id")
def test_add_item_duplicate(mock_get_list, mock_find_item, mock_can_view):
    db = MagicMock()
    user = SimpleNamespace(id=5)
    col = _make_folder(id=1, owner_id=5)
    gift_list = _make_gift_list(id=10, owner_id=5)
    mock_get_list.return_value = gift_list
    mock_find_item.return_value = _make_folder_item()

    with pytest.raises(ConflictError):
        service.add_item(db, folder=col, list_id=10, user=user)


@patch(f"{REPO}.get_gift_list_by_id", return_value=None)
def test_add_item_list_not_found(mock_get_list):
    # List existence is checked before access, so can_view_list is never reached.
    db = MagicMock()
    user = SimpleNamespace(id=5)
    col = _make_folder(id=1, owner_id=5)

    with pytest.raises(NotFoundError):
        service.add_item(db, folder=col, list_id=999, user=user)


# --- remove_item ---


@patch(f"{REPO}.delete_folder_item")
@patch(f"{REPO}.find_folder_item")
def test_remove_item(mock_find, mock_delete):
    db = MagicMock()
    col = _make_folder(id=1)
    item = _make_folder_item(folder_id=1, list_id=10)
    mock_find.return_value = item

    service.remove_item(db, folder=col, list_id=10)

    mock_find.assert_called_once_with(db, 1, 10)
    mock_delete.assert_called_once_with(db, item)


@patch(f"{REPO}.find_folder_item", return_value=None)
def test_remove_item_not_found(mock_find):
    db = MagicMock()
    col = _make_folder(id=1)

    with pytest.raises(NotFoundError):
        service.remove_item(db, folder=col, list_id=999)


@patch("app.folders.service.budgets_service")
@patch("app.folders.service.claims_repo.get_shopping_for_folder")
def test_get_shopping_reads_the_callers_own_claims(mock_shopping, budgets_service):
    """The claim query lives in the claims repository, and the caller's id is
    passed to it — a folder's shopping tab has no way to ask for anyone
    else's. The budget rollup beside it is keyed on the same id."""
    db = MagicMock()
    mock_shopping.return_value = [{"name": "Skillet"}]
    budgets_service.get_rollup.return_value = {"amount": None}

    result = service.get_shopping(db, folder_id=1, user_id=7)

    mock_shopping.assert_called_once_with(db, 1, 7)
    budgets_service.get_rollup.assert_called_once_with(db, user_id=7, folder_id=1)
    assert result == {"budget": {"amount": None}, "items": [{"name": "Skillet"}]}


@patch("app.folders.service.budgets_service")
def test_set_budget_is_scoped_to_the_folder_and_the_caller(budgets_service):
    db = MagicMock()
    budgets_service.set_budget.return_value = {"amount": Decimal("50.00")}

    result = service.set_budget(db, folder_id=1, user_id=7, amount=Decimal("50.00"))

    budgets_service.set_budget.assert_called_once_with(
        db, user_id=7, folder_id=1, amount=Decimal("50.00")
    )
    assert result == {"amount": Decimal("50.00")}


@patch("app.folders.service.budgets_repo")
@patch(f"{REPO}.delete_folder")
def test_delete_folder_takes_its_budget_with_it(mock_delete, budgets_repo):
    """`budgets.folder_id` points at the folder, so the budget goes first —
    the foreign key would refuse the delete otherwise."""
    db = MagicMock()
    folder = _make_folder(id=3)

    service.delete_folder(db, folder)

    budgets_repo.delete_budgets_for_folder.assert_called_once_with(db, 3)
    mock_delete.assert_called_once_with(db, folder)
