"""Unit tests for the per-family list sharing service (NEU-1202).

The repo layer is mocked throughout; these pin the branching rules — full mode
vs simple mode on create, the full-mode gate on the mutations, and the claim
handling on revoke.
"""
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.list_families import service
from app.services.exceptions import ConflictError, ForbiddenError

REPO = "app.list_families.service.repo"
FAMILIES_REPO = "app.list_families.service.families_repo"


def _user(user_id=1, simple_mode=False):
    return SimpleNamespace(id=user_id, simple_mode=simple_mode)


def _list(list_id=5, owner_id=1):
    return SimpleNamespace(id=list_id, owner_id=owner_id)


@pytest.fixture
def db():
    return MagicMock()


# ---------------------------------------------------------------------------
# list_family_states
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_families_for_user")
@patch(f"{REPO}.granted_family_ids")
def test_list_family_states_flags_each_of_the_owners_families(
    mock_granted, mock_families, db
):
    mock_granted.return_value = {2}
    mock_families.return_value = [
        SimpleNamespace(id=2, name="The Boones"),
        SimpleNamespace(id=3, name="The Smiths"),
    ]

    assert service.list_family_states(db, _list()) == [
        {"id": 2, "name": "The Boones", "shared": True},
        {"id": 3, "name": "The Smiths", "shared": False},
    ]
    # Scoped to the owner's families, not the caller's.
    mock_families.assert_called_once_with(db, 1)


# ---------------------------------------------------------------------------
# set_grants_on_create  (§2.4)
# ---------------------------------------------------------------------------


@patch(f"{REPO}.create_grant")
@patch(f"{FAMILIES_REPO}.family_ids_for_user")
def test_simple_mode_create_grants_all_families_and_ignores_the_body(
    mock_family_ids, mock_create, db
):
    mock_family_ids.return_value = {7, 8}
    service.set_grants_on_create(db, _list(), _user(simple_mode=True), family_ids=[])

    assert sorted(call.args[2] for call in mock_create.call_args_list) == [7, 8]


@patch(f"{REPO}.create_grant")
@patch(f"{FAMILIES_REPO}.family_ids_for_user")
def test_simple_mode_create_ignores_explicit_family_ids(
    mock_family_ids, mock_create, db
):
    mock_family_ids.return_value = {7}
    service.set_grants_on_create(db, _list(), _user(simple_mode=True), family_ids=[99])

    assert [call.args[2] for call in mock_create.call_args_list] == [7]


@patch(f"{REPO}.create_grant")
@patch(f"{FAMILIES_REPO}.get_family_member")
def test_full_mode_create_grants_exactly_the_requested_families(
    mock_member, mock_create, db
):
    mock_member.return_value = object()
    service.set_grants_on_create(db, _list(), _user(), family_ids=[7, 8])

    assert [call.args[2] for call in mock_create.call_args_list] == [7, 8]


@patch(f"{REPO}.create_grant")
@patch(f"{FAMILIES_REPO}.get_family_member")
def test_full_mode_create_deduplicates_family_ids(mock_member, mock_create, db):
    mock_member.return_value = object()
    service.set_grants_on_create(db, _list(), _user(), family_ids=[7, 7, 8])

    assert [call.args[2] for call in mock_create.call_args_list] == [7, 8]


@patch(f"{REPO}.create_grant")
@patch(f"{FAMILIES_REPO}.family_ids_for_user")
def test_full_mode_create_with_no_family_ids_grants_nothing(
    mock_family_ids, mock_create, db
):
    service.set_grants_on_create(db, _list(), _user(), family_ids=[])

    mock_create.assert_not_called()
    # Full mode must never fall back to "all my families".
    mock_family_ids.assert_not_called()


@patch(f"{REPO}.create_grant")
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=None)
def test_full_mode_create_with_a_foreign_family_raises_forbidden(
    mock_member, mock_create, db
):
    with pytest.raises(ForbiddenError):
        service.set_grants_on_create(db, _list(), _user(), family_ids=[99])
    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# create_grant / revoke_grant gating  (§2.6)
# ---------------------------------------------------------------------------


@patch(f"{REPO}.create_grant")
def test_create_grant_forbidden_in_simple_mode(mock_create, db):
    with pytest.raises(ForbiddenError, match="Switch to full mode"):
        service.create_grant(db, _list(), 7, _user(simple_mode=True))
    mock_create.assert_not_called()


@patch(f"{REPO}.delete_grant")
def test_revoke_grant_forbidden_in_simple_mode(mock_delete, db):
    with pytest.raises(ForbiddenError, match="Switch to full mode"):
        service.revoke_grant(db, _list(), 7, _user(simple_mode=True))
    mock_delete.assert_not_called()


@patch(f"{REPO}.create_grant")
@patch(f"{REPO}.find_grant", return_value=object())
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=object())
def test_create_grant_is_idempotent(mock_member, mock_find, mock_create, db):
    service.create_grant(db, _list(), 7, _user())
    mock_create.assert_not_called()


@patch(f"{REPO}.create_grant")
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=None)
def test_create_grant_for_a_foreign_family_raises_forbidden(
    mock_member, mock_create, db
):
    with pytest.raises(ForbiddenError):
        service.create_grant(db, _list(), 99, _user())
    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# revoke_grant claim handling  (§2.7)
# ---------------------------------------------------------------------------


@contextmanager
def _revoking(losing_ids, has_claims):
    """Patch out everything revoke_grant touches, yielding the three mocks whose
    call/no-call is the actual behaviour under test."""
    with ExitStack() as stack:
        for target, value in [
            (f"{FAMILIES_REPO}.get_family_member", object()),
            (f"{REPO}.find_grant", object()),
            (f"{REPO}.get_member_ids_losing_access", losing_ids),
            (f"{REPO}.any_claims_by_users", has_claims),
        ]:
            stack.enter_context(patch(target, return_value=value))
        yield SimpleNamespace(
            delete_grant=stack.enter_context(patch(f"{REPO}.delete_grant")),
            unclaim=stack.enter_context(patch(f"{REPO}.unclaim_for_users")),
            delete_items=stack.enter_context(
                patch(f"{REPO}.delete_collection_items_for_users")
            ),
        )


def test_revoke_without_a_choice_blocks_on_a_claim(db):
    with _revoking([2], has_claims=True) as m:
        with pytest.raises(ConflictError, match="claimed by members of this family"):
            service.revoke_grant(db, _list(), 7, _user())
        # Nothing changes on the blocked path.
        m.delete_grant.assert_not_called()
        m.unclaim.assert_not_called()
        m.delete_items.assert_not_called()


def test_revoke_release_unclaims_for_the_members_who_lose_access(db):
    with _revoking([2, 3], has_claims=True) as m:
        service.revoke_grant(db, _list(), 7, _user(), claims="release")
        m.delete_grant.assert_called_once()
        m.unclaim.assert_called_once_with(db, 5, [2, 3])
        m.delete_items.assert_called_once_with(db, 5, [2, 3])


def test_revoke_keep_leaves_claims_but_still_drops_collection_items(db):
    with _revoking([2], has_claims=True) as m:
        service.revoke_grant(db, _list(), 7, _user(), claims="keep")
        m.delete_grant.assert_called_once()
        m.unclaim.assert_not_called()
        m.delete_items.assert_called_once_with(db, 5, [2])


def test_revoke_without_a_choice_proceeds_when_no_claims_are_affected(db):
    with _revoking([2], has_claims=False) as m:
        service.revoke_grant(db, _list(), 7, _user())
        m.delete_grant.assert_called_once()
        m.unclaim.assert_not_called()
        m.delete_items.assert_called_once_with(db, 5, [2])


@patch(f"{REPO}.delete_grant")
@patch(f"{REPO}.find_grant", return_value=None)
@patch(f"{FAMILIES_REPO}.get_family_member", return_value=object())
def test_revoke_a_missing_grant_is_a_noop(mock_member, mock_find, mock_delete, db):
    service.revoke_grant(db, _list(), 7, _user())
    mock_delete.assert_not_called()


# ---------------------------------------------------------------------------
# grant_existing_lists_on_join  (§2.5)
# ---------------------------------------------------------------------------


@patch(f"{REPO}.grant_all_lists_to_family")
def test_join_auto_grants_for_a_simple_mode_member(mock_grant_all, db):
    service.grant_existing_lists_on_join(db, _user(user_id=4, simple_mode=True), 7)
    mock_grant_all.assert_called_once_with(db, owner_id=4, family_id=7)


@patch(f"{REPO}.grant_all_lists_to_family")
def test_join_grants_nothing_for_a_full_mode_member(mock_grant_all, db):
    service.grant_existing_lists_on_join(db, _user(user_id=4), 7)
    mock_grant_all.assert_not_called()
