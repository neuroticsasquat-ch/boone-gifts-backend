"""Unit tests for the share-to-an-occasion service (NEU-1265).

The repo layer is mocked throughout; these pin the sharing rules on create, the
membership and archived gates on the mutations, and the claim handling on
revoke.
"""
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.list_occasions import service
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

REPO = "app.list_occasions.service.repo"
CLAIMS_REPO = "app.list_occasions.service.claims_repo"
FAMILIES_REPO = "app.list_occasions.service.families_repo"
OCCASIONS_REPO = "app.list_occasions.service.occasions_repo"


def _user(user_id=1):
    return SimpleNamespace(id=user_id)


def _list(list_id=5, owner_id=1):
    return SimpleNamespace(id=list_id, owner_id=owner_id)


def _occasion(occasion_id=7, family_id=2, name="Christmas 2026", is_archived=False):
    return SimpleNamespace(
        id=occasion_id, family_id=family_id, name=name, is_archived=is_archived
    )


@pytest.fixture
def db():
    return MagicMock()


# ---------------------------------------------------------------------------
# list_share_targets
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_member_ids_for_families")
@patch(f"{REPO}.get_occasions_for_families")
@patch(f"{REPO}.get_families_for_user")
@patch(f"{REPO}.shared_occasion_ids")
def test_list_share_targets_groups_occasions_under_their_family(
    mock_shared, mock_families, mock_occasions, mock_members, db
):
    mock_shared.return_value = {10}
    mock_families.return_value = [
        SimpleNamespace(id=2, name="The Boones"),
        SimpleNamespace(id=3, name="The Smiths"),
    ]
    mock_occasions.return_value = [
        _occasion(10, 2, "Christmas 2026"),
        _occasion(11, 2, "Gran's 80th"),
        _occasion(12, 3, "Christmas 2026"),
    ]
    mock_members.return_value = {2: [1, 4], 3: [1, 9]}

    assert service.list_share_targets(db, _list()) == [
        {
            "id": 2,
            "name": "The Boones",
            "member_ids": [1, 4],
            "occasions": [
                {
                    "id": 10,
                    "name": "Christmas 2026",
                    "is_archived": False,
                    "shared": True,
                },
                {
                    "id": 11,
                    "name": "Gran's 80th",
                    "is_archived": False,
                    "shared": False,
                },
            ],
        },
        {
            "id": 3,
            "name": "The Smiths",
            "member_ids": [1, 9],
            "occasions": [
                {
                    "id": 12,
                    "name": "Christmas 2026",
                    "is_archived": False,
                    "shared": False,
                }
            ],
        },
    ]
    # Scoped to the owner's families, not the caller's.
    mock_families.assert_called_once_with(db, 1)


@patch(f"{REPO}.get_member_ids_for_families", return_value={2: [1]})
@patch(f"{REPO}.get_occasions_for_families")
@patch(f"{REPO}.get_families_for_user")
@patch(f"{REPO}.shared_occasion_ids")
def test_list_share_targets_hides_an_archived_occasion_unless_shared_to(
    mock_shared, mock_families, mock_occasions, mock_members, db
):
    """An archived occasion is not a shareable target, so it only earns a row
    when the list is already on it and its name still has to be displayable."""
    mock_shared.return_value = {11}
    mock_families.return_value = [SimpleNamespace(id=2, name="The Boones")]
    mock_occasions.return_value = [
        _occasion(10, 2, "Christmas 2024", is_archived=True),
        _occasion(11, 2, "Christmas 2025", is_archived=True),
    ]

    (family,) = service.list_share_targets(db, _list())
    assert family["occasions"] == [
        {"id": 11, "name": "Christmas 2025", "is_archived": True, "shared": True}
    ]


@patch(f"{REPO}.get_member_ids_for_families", return_value={2: [1]})
@patch(f"{REPO}.get_occasions_for_families", return_value=[])
@patch(f"{REPO}.get_families_for_user")
@patch(f"{REPO}.shared_occasion_ids", return_value=set())
def test_list_share_targets_keeps_a_family_with_no_occasions(
    mock_shared, mock_families, mock_occasions, mock_members, db
):
    """A family with no active occasion cannot be shared to, but it is still
    listed — the control renders it disabled with the reason."""
    mock_families.return_value = [SimpleNamespace(id=2, name="Work Friends")]

    assert service.list_share_targets(db, _list()) == [
        {"id": 2, "name": "Work Friends", "member_ids": [1], "occasions": []}
    ]


@patch(f"{REPO}.get_member_ids_for_families")
@patch(f"{REPO}.get_occasions_for_families", return_value=[])
@patch(f"{REPO}.get_families_for_user")
@patch(f"{REPO}.shared_occasion_ids", return_value=set())
def test_list_share_targets_asks_for_every_family_s_members_at_once(
    mock_shared, mock_families, mock_occasions, mock_members, db
):
    """One batched call over all the families, not one per family — the field is
    decoration on a payload already being assembled (NEU-1285 §1)."""
    mock_families.return_value = [
        SimpleNamespace(id=2, name="The Boones"),
        SimpleNamespace(id=3, name="The Smiths"),
    ]
    mock_members.return_value = {2: [1, 4], 3: [1]}

    targets = service.list_share_targets(db, _list())

    mock_members.assert_called_once_with(db, [2, 3])
    assert [t["member_ids"] for t in targets] == [[1, 4], [1]]


# ---------------------------------------------------------------------------
# set_shares_on_create
# ---------------------------------------------------------------------------


@patch(f"{REPO}.create_share")
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=object())
@patch(f"{OCCASIONS_REPO}.get_occasion", side_effect=lambda db, i: _occasion(i))
def test_create_shares_exactly_the_requested_occasions(
    mock_get, mock_member, mock_create, db
):
    service.set_shares_on_create(db, _list(), _user(), occasion_ids=[7, 8])

    assert [call.args[2] for call in mock_create.call_args_list] == [7, 8]


@patch(f"{REPO}.create_share")
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=object())
@patch(f"{OCCASIONS_REPO}.get_occasion", side_effect=lambda db, i: _occasion(i))
def test_create_deduplicates_occasion_ids(mock_get, mock_member, mock_create, db):
    service.set_shares_on_create(db, _list(), _user(), occasion_ids=[7, 7, 8])

    assert [call.args[2] for call in mock_create.call_args_list] == [7, 8]


@patch(f"{REPO}.create_share")
@patch(f"{OCCASIONS_REPO}.get_occasion")
def test_create_with_no_occasion_ids_shares_nothing(mock_get, mock_create, db):
    service.set_shares_on_create(db, _list(), _user(), occasion_ids=[])

    mock_create.assert_not_called()
    # Creation must never fall back to "all my occasions" — the simple-mode
    # auto-grant is gone (ADR 0004) and nothing replaces it server-side.
    mock_get.assert_not_called()


@patch(f"{REPO}.create_share")
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=None)
@patch(f"{OCCASIONS_REPO}.get_occasion", side_effect=lambda db, i: _occasion(i))
def test_create_with_a_foreign_occasion_raises_forbidden(
    mock_get, mock_member, mock_create, db
):
    with pytest.raises(ForbiddenError):
        service.set_shares_on_create(db, _list(), _user(), occasion_ids=[99])
    mock_create.assert_not_called()


@patch(f"{REPO}.create_share")
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=object())
@patch(f"{OCCASIONS_REPO}.get_occasion")
def test_create_writes_nothing_when_a_later_occasion_is_archived(
    mock_get, mock_member, mock_create, db
):
    """Validation runs over every id before any share is written, so a bad one
    partway through cannot leave the earlier shares behind."""
    mock_get.side_effect = lambda db, i: _occasion(i, is_archived=(i == 8))

    with pytest.raises(ConflictError):
        service.set_shares_on_create(db, _list(), _user(), occasion_ids=[7, 8])
    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# create_share / revoke_share gating
# ---------------------------------------------------------------------------


@patch(f"{REPO}.create_share")
@patch(f"{REPO}.find_share", return_value=object())
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=object())
@patch(f"{OCCASIONS_REPO}.get_occasion", return_value=_occasion())
def test_create_share_is_idempotent(mock_get, mock_member, mock_find, mock_create, db):
    service.create_share(db, _list(), 7, _user())
    mock_create.assert_not_called()


@patch(f"{REPO}.create_share")
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=None)
@patch(f"{OCCASIONS_REPO}.get_occasion", return_value=_occasion())
def test_create_share_for_a_foreign_occasion_raises_forbidden(
    mock_get, mock_member, mock_create, db
):
    with pytest.raises(ForbiddenError):
        service.create_share(db, _list(), 7, _user())
    mock_create.assert_not_called()


@patch(f"{REPO}.create_share")
@patch(f"{FAMILIES_REPO}.get_family_member")
@patch(f"{OCCASIONS_REPO}.get_occasion", return_value=None)
def test_create_share_for_a_missing_occasion_raises_not_found(
    mock_get, mock_member, mock_create, db
):
    with pytest.raises(NotFoundError):
        service.create_share(db, _list(), 7, _user())
    # Membership is never consulted for an occasion that does not exist.
    mock_member.assert_not_called()
    mock_create.assert_not_called()


@patch(f"{REPO}.create_share")
@patch(f"{REPO}.find_share", return_value=None)
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=object())
@patch(f"{OCCASIONS_REPO}.get_occasion", return_value=_occasion(is_archived=True))
def test_create_share_on_an_archived_occasion_raises_conflict(
    mock_get, mock_member, mock_find, mock_create, db
):
    with pytest.raises(ConflictError, match="archived"):
        service.create_share(db, _list(), 7, _user())
    mock_create.assert_not_called()


@patch(f"{FAMILIES_REPO}.get_family_member", return_value=None)
@patch(f"{OCCASIONS_REPO}.get_occasion", return_value=_occasion(is_archived=True))
def test_create_share_checks_membership_before_revealing_archived_state(
    mock_get, mock_member, db
):
    """A non-member gets the same 403 whatever the occasion's state — they learn
    nothing about a family they do not belong to."""
    with pytest.raises(ForbiddenError):
        service.create_share(db, _list(), 7, _user())


# ---------------------------------------------------------------------------
# revoke_share claim handling
# ---------------------------------------------------------------------------


@contextmanager
def _revoking(losing_ids, has_claims, occasion=None):
    """Patch out everything revoke_share touches, yielding the three mocks whose
    call/no-call is the actual behaviour under test."""
    with ExitStack() as stack:
        for target, value in [
            (f"{OCCASIONS_REPO}.get_occasion", occasion or _occasion()),
            (f"{FAMILIES_REPO}.get_family_member", object()),
            (f"{REPO}.find_share", object()),
            (f"{REPO}.get_member_ids_losing_access", losing_ids),
            (f"{CLAIMS_REPO}.any_claims_by_users", has_claims),
        ]:
            stack.enter_context(patch(target, return_value=value))
        yield SimpleNamespace(
            delete_share=stack.enter_context(patch(f"{REPO}.delete_share")),
            unclaim=stack.enter_context(patch(f"{CLAIMS_REPO}.unclaim_for_users")),
            delete_items=stack.enter_context(
                patch(f"{REPO}.delete_folder_items_for_users")
            ),
        )


def test_revoke_without_a_choice_blocks_on_a_claim(db):
    with _revoking([2], has_claims=True) as m:
        with pytest.raises(ConflictError, match="claimed by members of this family"):
            service.revoke_share(db, _list(), 7, _user())
        # Nothing changes on the blocked path.
        m.delete_share.assert_not_called()
        m.unclaim.assert_not_called()
        m.delete_items.assert_not_called()


def test_revoke_release_unclaims_for_the_members_who_lose_access(db):
    with _revoking([2, 3], has_claims=True) as m:
        service.revoke_share(db, _list(), 7, _user(), claims="release")
        m.delete_share.assert_called_once()
        m.unclaim.assert_called_once_with(db, 5, [2, 3])
        m.delete_items.assert_called_once_with(db, 5, [2, 3])


def test_revoke_keep_leaves_claims_but_still_drops_folder_items(db):
    with _revoking([2], has_claims=True) as m:
        service.revoke_share(db, _list(), 7, _user(), claims="keep")
        m.delete_share.assert_called_once()
        m.unclaim.assert_not_called()
        m.delete_items.assert_called_once_with(db, 5, [2])


def test_revoke_without_a_choice_proceeds_when_no_claims_are_affected(db):
    with _revoking([2], has_claims=False) as m:
        service.revoke_share(db, _list(), 7, _user())
        m.delete_share.assert_called_once()
        m.unclaim.assert_not_called()
        m.delete_items.assert_called_once_with(db, 5, [2])


def test_revoke_works_on_an_archived_occasion(db):
    """Archiving blocks new shares, not the withdrawal of an old one."""
    with _revoking([2], has_claims=False, occasion=_occasion(is_archived=True)) as m:
        service.revoke_share(db, _list(), 7, _user())
        m.delete_share.assert_called_once()


@patch(f"{REPO}.delete_share")
@patch(f"{REPO}.find_share", return_value=None)
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=object())
@patch(f"{OCCASIONS_REPO}.get_occasion", return_value=_occasion())
def test_revoke_a_missing_share_is_a_noop(
    mock_get, mock_member, mock_find, mock_delete, db
):
    service.revoke_share(db, _list(), 7, _user())
    mock_delete.assert_not_called()
