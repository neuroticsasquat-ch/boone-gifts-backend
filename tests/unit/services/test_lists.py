from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.lists import service
from app.models.gift_list import GiftList
from app.schemas.gift_list import (
    DirectShareRoute,
    GiftListDetailOwner,
    GiftListDetailViewer,
    GiftListRead,
    NamedRef,
    OccasionShareRoute,
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
    # Explicit, because MagicMock(spec=...) hands back a truthy mock for any
    # attribute left unset — and the service reads both of these to judge the
    # person/recipient exclusivity of the resulting row.
    gl.recipient_name = None
    gl.account_person_id = None
    gl.account_person_name = None
    gl.is_archived = False
    gl.gift_count = 0
    gl.shared_via = []
    gl.created_at = datetime(2026, 1, 1)
    gl.updated_at = datetime(2026, 1, 1)
    return gl


REPO = "app.lists.service.repo"
CLAIMS_REPO = "app.lists.service.claims_repo"
LIST_OCCASION_SVC = "app.lists.service.list_occasion_service"


@pytest.fixture
def no_routes():
    """`to_summaries` asks the repository for share routes on every list-row
    response. Tests about anything else stub it away rather than restate it."""
    with patch(f"{REPO}.get_share_routes", return_value={}) as mock:
        yield mock


# --- create_list ---


@patch(f"{LIST_OCCASION_SVC}.set_shares_on_create")
@patch(f"{REPO}.create_list")
def test_create_list(mock_create, mock_shares):
    db = MagicMock()
    owner = SimpleNamespace(id=1)
    expected = _make_gift_list()
    mock_create.return_value = expected

    result = service.create_list(
        db, name="My List", description="A test list", owner=owner, occasion_ids=[7]
    )

    mock_create.assert_called_once_with(
        db,
        name="My List",
        description="A test list",
        owner_id=1,
        recipient_name=None,
        account_person_id=None,
    )
    mock_shares.assert_called_once_with(db, expected, owner, [7])
    assert result == expected


@patch(f"{LIST_OCCASION_SVC}.set_shares_on_create")
@patch(f"{REPO}.create_list")
def test_create_list_without_occasion_ids_passes_empty_list(mock_create, mock_shares):
    db = MagicMock()
    owner = SimpleNamespace(id=1)
    mock_create.return_value = _make_gift_list()

    service.create_list(db, name="My List", description=None, owner=owner)

    mock_shares.assert_called_once_with(db, mock_create.return_value, owner, [])


# --- get_lists (filter logic) ---


@patch(f"{REPO}.get_lists_by_owner")
def test_get_lists_owned(mock_get_owned, no_routes):
    db = MagicMock()
    lists = [_make_gift_list(id=1), _make_gift_list(id=2)]
    mock_get_owned.return_value = lists

    result = service.get_lists(db, user_id=1, filter="owned")

    mock_get_owned.assert_called_once_with(db, 1, archived=False)
    assert len(result) == 2


@patch(f"{REPO}.get_lists_by_ids")
@patch(f"{REPO}.get_share_routes", return_value={3: []})
def test_get_lists_shared(mock_routes, mock_by_ids):
    db = MagicMock()
    mock_by_ids.return_value = [_make_gift_list(id=3, owner_id=2)]

    result = service.get_lists(db, user_id=1, filter="shared")

    # The scope comes from the route keys, not from a second union.
    mock_by_ids.assert_called_once_with(db, [3], archived=False)
    assert len(result) == 1


@patch(f"{REPO}.get_all_visible_lists")
def test_get_lists_all(mock_get_all, no_routes):
    db = MagicMock()
    lists = [_make_gift_list(id=1), _make_gift_list(id=3, owner_id=2)]
    mock_get_all.return_value = lists

    result = service.get_lists(db, user_id=1, filter=None)

    mock_get_all.assert_called_once_with(db, 1, archived=False)
    assert len(result) == 2


# --- get_list (owner vs viewer) ---


@patch("app.lists.service.claim_service.occasion_sets")
@patch("app.lists.service.GiftListDetailOwner.model_validate")
def test_get_list_as_owner(mock_validate, mock_sets):
    gift_list = _make_gift_list(owner_id=5)
    expected = MagicMock(spec=GiftListDetailOwner)
    mock_validate.return_value = expected

    result = service.get_list(MagicMock(), gift_list, SimpleNamespace(id=5))

    mock_validate.assert_called_once_with(gift_list)
    assert result == expected
    # The owner's detail is never even asked what a claim could be filed under.
    mock_sets.assert_not_called()


@patch("app.lists.service.claim_service.occasion_sets")
@patch("app.lists.service.GiftListDetailViewer.model_validate")
def test_get_list_as_viewer(mock_validate, mock_sets):
    gift_list = _make_gift_list(owner_id=5)
    expected = MagicMock(spec=GiftListDetailViewer)
    mock_validate.return_value = expected
    allowed, suggested = ["allowed"], ["suggested"]
    mock_sets.return_value = (allowed, suggested)
    db, viewer = MagicMock(), SimpleNamespace(id=10)

    result = service.get_list(db, gift_list, viewer)

    mock_validate.assert_called_once_with(gift_list)
    mock_sets.assert_called_once_with(db, gift_list, viewer)
    # candidates is `suggested`, options is `allowed` — swapping them would
    # prompt on every claim and hide the correction path.
    assert result.claim_candidates == suggested
    assert result.claim_options == allowed
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
@patch(f"{CLAIMS_REPO}.has_claimed_gifts", return_value=False)
def test_delete_list(mock_has_claims, mock_delete):
    db = MagicMock()
    gift_list = _make_gift_list()

    service.delete_list(db, gift_list)

    mock_has_claims.assert_called_once_with(db, gift_list.id)
    mock_delete.assert_called_once_with(db, gift_list)


@patch(f"{CLAIMS_REPO}.has_claimed_gifts", return_value=True)
def test_delete_list_blocked_by_claims(mock_has_claims):
    from app.services.exceptions import ConflictError

    db = MagicMock()
    gift_list = _make_gift_list()

    with pytest.raises(ConflictError, match="claimed"):
        service.delete_list(db, gift_list)


# --- GiftListRead.shared_via (a list of routes) ---


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
        account_person_id=None,
        account_person_name=None,
        is_archived=False,
        gifts=[],
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
    )
    if shared_via is not None:
        obj.shared_via = shared_via
    return obj


def test_gift_list_read_includes_every_route():
    """A list reaching the viewer both ways reports both routes — the discard
    this ticket removes."""
    obj = _read_source(
        shared_via=[
            {"kind": "direct", "person": {"id": 2, "name": "Jane Boone"}},
            {
                "kind": "occasion",
                "occasion": {"id": 3, "name": "Christmas 2026"},
                "family": {"id": 1, "name": "Boone Family"},
            },
        ]
    )
    result = GiftListRead.model_validate(obj)
    direct, occasion = result.shared_via
    assert (direct.person.id, direct.person.name) == (2, "Jane Boone")
    assert (occasion.occasion.id, occasion.occasion.name) == (3, "Christmas 2026")
    assert (occasion.family.id, occasion.family.name) == (1, "Boone Family")


def test_kind_discriminates_which_route_a_payload_becomes():
    """The arms carry different payloads, so `kind` picks the model. The flat
    schema needed a validator to refuse the mismatched combinations; the union
    cannot represent them."""
    result = GiftListRead.model_validate(
        _read_source(
            shared_via=[{"kind": "direct", "person": {"id": 2, "name": "Jane"}}]
        )
    )
    assert isinstance(result.shared_via[0], DirectShareRoute)


def test_an_occasion_route_without_its_family_is_refused():
    """The occasion arm always carries `family: {id, name}`; a missing one would
    be a shape the client cannot render."""
    with pytest.raises(ValidationError):
        OccasionShareRoute(
            kind="occasion", occasion=NamedRef(id=3, name="Christmas 2026")
        )


def test_a_direct_route_has_no_family_field_to_set():
    """There is no occasion behind a direct share, so there is no family
    either — and no way to attach one."""
    route = DirectShareRoute(
        kind="direct", person=NamedRef(id=2, name="Jane Boone")
    )
    assert "family" not in route.model_dump()


def test_gift_list_read_shared_via_defaults_to_an_empty_list():
    obj = _read_source()  # no shared_via attribute set — an owned list
    result = GiftListRead.model_validate(obj)
    assert result.shared_via == []


# --- to_summaries (the seam that annotates every list row) ---


@patch(f"{REPO}.get_share_routes")
def test_to_summaries_annotates_each_row_with_its_routes(mock_routes):
    db = MagicMock()
    gl1, gl2 = _make_gift_list(id=10, owner_id=2), _make_gift_list(id=20, owner_id=2)
    direct = DirectShareRoute(kind="direct", person=NamedRef(id=2, name="Jane Boone"))
    occasion = OccasionShareRoute(
        kind="occasion",
        occasion=NamedRef(id=3, name="Christmas 2026"),
        family=NamedRef(id=1, name="Boone Family"),
    )
    mock_routes.return_value = {10: [direct, occasion]}

    result = service.to_summaries(db, [gl1, gl2], viewer_id=5)

    # One batched call for the whole page, not one per row.
    mock_routes.assert_called_once_with(db, 5, [10, 20])
    assert result[0].shared_via == [direct, occasion]
    # Absent from the mapping is an empty array, never null.
    assert result[1].shared_via == []


@patch(f"{REPO}.get_share_routes", return_value={})
def test_to_summaries_does_not_ask_about_rows_the_caller_owns(mock_routes):
    """Both arms of the union exclude the caller's own lists, so a route query
    about an owned row can only come back empty. Only the rest are asked about."""
    db = MagicMock()
    owned = _make_gift_list(id=10, owner_id=5)
    shared = _make_gift_list(id=20, owner_id=2)

    result = service.to_summaries(db, [owned, shared], viewer_id=5)

    mock_routes.assert_called_once_with(db, 5, [20])
    # The owned row still gets its empty array — it is skipped in the query, not
    # in the annotation.
    assert result[0].shared_via == []


@patch(f"{REPO}.get_share_routes", return_value={})
def test_to_summaries_still_picks_the_schema_per_row(mock_routes):
    """It wraps `to_summary` rather than replacing it: the owner-vs-viewer
    choice stays in one place (ADR 0003)."""
    db = MagicMock()
    owned, shared = _make_gift_list(id=10, owner_id=5), _make_gift_list(id=20, owner_id=2)

    result = service.to_summaries(db, [owned, shared], viewer_id=5)

    assert not hasattr(result[0], "claimed_count")
    assert result[1].claimed_count == 0


# --- get_shared_lists (the scope comes from the routes) ---


@patch(f"{REPO}.get_lists_by_ids")
@patch(f"{REPO}.get_share_routes")
def test_get_shared_lists_takes_its_scope_from_the_route_keys(
    mock_routes, mock_by_ids
):
    db = MagicMock()
    direct = DirectShareRoute(kind="direct", person=NamedRef(id=2, name="Jane Boone"))
    mock_routes.return_value = {10: [direct], 20: [direct]}
    mock_by_ids.return_value = ["rows"]

    result = service.get_shared_lists(db, user_id=5)

    # `list_ids=None` — the whole shared scope, so the union defining it is
    # written once and cannot drift from a second copy.
    mock_routes.assert_called_once_with(db, 5)
    mock_by_ids.assert_called_once_with(db, [10, 20], archived=False)
    assert result == ["rows"]


@patch(f"{REPO}.get_lists_by_ids", return_value=[])
@patch(f"{REPO}.get_share_routes", return_value={})
def test_get_shared_lists_empty(mock_routes, mock_by_ids):
    assert service.get_shared_lists(MagicMock(), user_id=5) == []


@patch(f"{REPO}.get_lists_by_ids", return_value=[])
@patch(f"{REPO}.get_share_routes", return_value={10: []})
def test_get_lists_shared_archived_passthrough(mock_routes, mock_by_ids):
    """Routes say nothing about `archived`: an archived list still has them, it
    just belongs on the other page, so the flag is applied when the rows load."""
    db = MagicMock()

    service.get_lists(db, user_id=5, filter="shared", archived=True)

    mock_by_ids.assert_called_once_with(db, [10], archived=True)
