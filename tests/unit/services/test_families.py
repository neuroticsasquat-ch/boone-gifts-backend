from unittest.mock import MagicMock, patch

import pytest

from app.families import service
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.user import User
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError

REPO = "app.families.service.repo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_family(id: int = 1, name: str = "Smith Family", created_by_id: int = 10) -> MagicMock:
    family = MagicMock(spec=Family)
    family.id = id
    family.name = name
    family.created_by_id = created_by_id
    return family


def _make_member(
    id: int = 1,
    family_id: int = 1,
    user_id: int = 10,
    role: str = "organizer",
) -> MagicMock:
    member = MagicMock(spec=FamilyMember)
    member.id = id
    member.family_id = family_id
    member.user_id = user_id
    member.role = role
    return member


def _make_user(id: int = 10, name: str = "Alice") -> MagicMock:
    user = MagicMock(spec=User)
    user.id = id
    user.name = name
    return user


@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# create_family
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_family_members_with_users")
@patch(f"{REPO}.get_family")
@patch(f"{REPO}.create_family_member")
@patch(f"{REPO}.create_family")
def test_create_family_happy_path(
    mock_create_family,
    mock_create_member,
    mock_get_family,
    mock_get_members,
    db,
):
    family = _make_family(id=1, name="Smith Family", created_by_id=10)
    member = _make_member(id=1, family_id=1, user_id=10, role="organizer")
    user = _make_user(id=10, name="Alice")

    mock_create_family.return_value = family
    mock_create_member.return_value = member
    mock_get_family.return_value = family
    mock_get_members.return_value = [(member, user)]

    result = service.create_family(db, name="Smith Family", creator_id=10)

    mock_create_family.assert_called_once_with(db, name="Smith Family", created_by_id=10)
    mock_create_member.assert_called_once_with(db, family_id=1, user_id=10, role="organizer")
    assert result["id"] == 1
    assert result["name"] == "Smith Family"
    assert result["created_by_id"] == 10
    assert len(result["members"]) == 1
    assert result["members"][0] == {"user_id": 10, "name": "Alice", "role": "organizer"}


# ---------------------------------------------------------------------------
# list_families
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_member_count")
@patch(f"{REPO}.get_family")
@patch(f"{REPO}.get_user_memberships")
def test_list_families_happy_path(mock_get_memberships, mock_get_family, mock_get_count, db):
    member = _make_member(id=1, family_id=1, user_id=10, role="organizer")
    family = _make_family(id=1, name="Smith Family")

    mock_get_memberships.return_value = [member]
    mock_get_family.return_value = family
    mock_get_count.return_value = 3

    result = service.list_families(db, user_id=10)

    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["name"] == "Smith Family"
    assert result[0]["role"] == "organizer"
    assert result[0]["member_count"] == 3


@patch(f"{REPO}.get_user_memberships", return_value=[])
def test_list_families_empty(mock_get_memberships, db):
    result = service.list_families(db, user_id=10)
    assert result == []


@patch(f"{REPO}.get_member_count")
@patch(f"{REPO}.get_family")
@patch(f"{REPO}.get_user_memberships")
def test_list_families_skips_missing_family(
    mock_get_memberships, mock_get_family, mock_get_count, db
):
    member = _make_member(id=1, family_id=99, user_id=10, role="member")
    mock_get_memberships.return_value = [member]
    mock_get_family.return_value = None

    result = service.list_families(db, user_id=10)

    assert result == []
    mock_get_count.assert_not_called()


# ---------------------------------------------------------------------------
# get_family_detail
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_family", return_value=None)
def test_get_family_detail_not_found(mock_get_family, db):
    with pytest.raises(NotFoundError):
        service.get_family_detail(db, family_id=99, user_id=10)


@patch(f"{REPO}.get_family_member", return_value=None)
@patch(f"{REPO}.get_family")
def test_get_family_detail_not_a_member(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    with pytest.raises(ForbiddenError):
        service.get_family_detail(db, family_id=1, user_id=99)


@patch(f"{REPO}.get_family_members_with_users")
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_get_family_detail_happy_path(
    mock_get_family, mock_get_member, mock_get_members, db
):
    family = _make_family(id=1, name="Smith Family", created_by_id=10)
    member = _make_member(id=1, family_id=1, user_id=10, role="organizer")
    user = _make_user(id=10, name="Alice")

    mock_get_family.return_value = family
    mock_get_member.return_value = member
    mock_get_members.return_value = [(member, user)]

    result = service.get_family_detail(db, family_id=1, user_id=10)

    assert result["id"] == 1
    assert result["name"] == "Smith Family"
    assert result["created_by_id"] == 10
    assert result["members"][0]["user_id"] == 10
    assert result["members"][0]["name"] == "Alice"
    assert result["members"][0]["role"] == "organizer"


# ---------------------------------------------------------------------------
# rename_family
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_family", return_value=None)
def test_rename_family_not_found(mock_get_family, db):
    with pytest.raises(NotFoundError):
        service.rename_family(db, family_id=99, user_id=10, name="New Name")


@patch(f"{REPO}.get_family_member", return_value=None)
@patch(f"{REPO}.get_family")
def test_rename_family_not_a_member(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    with pytest.raises(ForbiddenError):
        service.rename_family(db, family_id=1, user_id=99, name="New Name")


@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_rename_family_not_organizer(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="member")
    with pytest.raises(ForbiddenError, match="organizer"):
        service.rename_family(db, family_id=1, user_id=10, name="New Name")


@patch(f"{REPO}.get_family_members_with_users")
@patch(f"{REPO}.update_family_name")
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_rename_family_happy_path(
    mock_get_family, mock_get_member, mock_update, mock_get_members, db
):
    family = _make_family(id=1, name="Old Name", created_by_id=10)
    member = _make_member(id=1, family_id=1, user_id=10, role="organizer")
    user = _make_user(id=10, name="Alice")

    # get_family is called twice: once for the guard, once inside _build_family_detail
    mock_get_family.return_value = family
    mock_get_member.return_value = member
    mock_get_members.return_value = [(member, user)]

    result = service.rename_family(db, family_id=1, user_id=10, name="New Name")

    mock_update.assert_called_once_with(db, family, "New Name")
    assert result["id"] == 1


# ---------------------------------------------------------------------------
# delete_family
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_family", return_value=None)
def test_delete_family_not_found(mock_get_family, db):
    with pytest.raises(NotFoundError):
        service.delete_family(db, family_id=99, user_id=10)


@patch(f"{REPO}.get_family_member", return_value=None)
@patch(f"{REPO}.get_family")
def test_delete_family_not_a_member(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    with pytest.raises(ForbiddenError):
        service.delete_family(db, family_id=1, user_id=99)


@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_delete_family_not_organizer(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(role="member")
    with pytest.raises(ForbiddenError, match="organizer"):
        service.delete_family(db, family_id=1, user_id=10)


@patch(f"{REPO}.delete_family")
@patch(f"{REPO}.delete_all_members")
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_delete_family_happy_path(
    mock_get_family, mock_get_member, mock_delete_members, mock_delete_family, db
):
    family = _make_family(id=1)
    member = _make_member(id=1, family_id=1, user_id=10, role="organizer")

    mock_get_family.return_value = family
    mock_get_member.return_value = member

    service.delete_family(db, family_id=1, user_id=10)

    mock_delete_members.assert_called_once_with(db, 1)
    mock_delete_family.assert_called_once_with(db, family)


# ---------------------------------------------------------------------------
# remove_member
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_family", return_value=None)
def test_remove_member_family_not_found(mock_get_family, db):
    with pytest.raises(NotFoundError):
        service.remove_member(db, family_id=99, actor_id=10, target_user_id=20)


@patch(f"{REPO}.get_family_member", return_value=None)
@patch(f"{REPO}.get_family")
def test_remove_member_actor_not_a_member(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    with pytest.raises(ForbiddenError):
        service.remove_member(db, family_id=1, actor_id=99, target_user_id=20)


@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_remove_member_target_not_a_member(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    actor = _make_member(user_id=10, role="organizer")
    mock_get_member.side_effect = [actor, None]  # actor found, target missing
    with pytest.raises(NotFoundError):
        service.remove_member(db, family_id=1, actor_id=10, target_user_id=20)


@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_remove_member_non_organizer_removing_other(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    actor = _make_member(user_id=10, role="member")
    target = _make_member(user_id=20, role="member")
    mock_get_member.side_effect = [actor, target]
    with pytest.raises(ForbiddenError, match="organizer"):
        service.remove_member(db, family_id=1, actor_id=10, target_user_id=20)


@patch(f"{REPO}.delete_family_member")
@patch(f"{REPO}.count_organizers")
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_remove_member_self_leave_as_member(
    mock_get_family, mock_get_member, mock_count, mock_delete, db
):
    mock_get_family.return_value = _make_family()
    member = _make_member(user_id=10, role="member")
    mock_get_member.side_effect = [member, member]  # actor == target
    service.remove_member(db, family_id=1, actor_id=10, target_user_id=10)
    mock_delete.assert_called_once_with(db, member)
    mock_count.assert_not_called()  # member target → guard short-circuits


@patch(f"{REPO}.delete_family_member")
@patch(f"{REPO}.count_organizers")
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_remove_member_organizer_removes_member(
    mock_get_family, mock_get_member, mock_count, mock_delete, db
):
    mock_get_family.return_value = _make_family()
    actor = _make_member(user_id=10, role="organizer")
    target = _make_member(user_id=20, role="member")
    mock_get_member.side_effect = [actor, target]
    service.remove_member(db, family_id=1, actor_id=10, target_user_id=20)
    mock_delete.assert_called_once_with(db, target)


@patch(f"{REPO}.delete_family_member")
@patch(f"{REPO}.count_organizers", return_value=2)
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_remove_member_organizer_removes_co_organizer(
    mock_get_family, mock_get_member, mock_count, mock_delete, db
):
    mock_get_family.return_value = _make_family()
    actor = _make_member(user_id=10, role="organizer")
    target = _make_member(user_id=20, role="organizer")
    mock_get_member.side_effect = [actor, target]
    service.remove_member(db, family_id=1, actor_id=10, target_user_id=20)
    mock_delete.assert_called_once_with(db, target)


@patch(f"{REPO}.delete_family_member")
@patch(f"{REPO}.count_organizers", return_value=2)
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_remove_member_organizer_self_leave_with_co_organizer(
    mock_get_family, mock_get_member, mock_count, mock_delete, db
):
    mock_get_family.return_value = _make_family()
    organizer = _make_member(user_id=10, role="organizer")
    mock_get_member.side_effect = [organizer, organizer]  # actor == target
    service.remove_member(db, family_id=1, actor_id=10, target_user_id=10)
    mock_delete.assert_called_once_with(db, organizer)
    mock_count.assert_called_once_with(db, 1)


@patch(f"{REPO}.delete_family_member")
@patch(f"{REPO}.count_organizers", return_value=1)
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_remove_member_last_organizer_raises_conflict(
    mock_get_family, mock_get_member, mock_count, mock_delete, db
):
    mock_get_family.return_value = _make_family()
    organizer = _make_member(user_id=10, role="organizer")
    mock_get_member.side_effect = [organizer, organizer]  # self-leave, sole organizer
    with pytest.raises(ConflictError):
        service.remove_member(db, family_id=1, actor_id=10, target_user_id=10)
    mock_delete.assert_not_called()


# ---------------------------------------------------------------------------
# update_member_role
# ---------------------------------------------------------------------------


@patch(f"{REPO}.get_family", return_value=None)
def test_update_role_family_not_found(mock_get_family, db):
    with pytest.raises(NotFoundError):
        service.update_member_role(
            db, family_id=99, actor_id=10, target_user_id=20, role="organizer"
        )


@patch(f"{REPO}.get_family_member", return_value=None)
@patch(f"{REPO}.get_family")
def test_update_role_actor_not_a_member(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    with pytest.raises(ForbiddenError):
        service.update_member_role(
            db, family_id=1, actor_id=99, target_user_id=20, role="organizer"
        )


@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_update_role_actor_not_organizer(mock_get_family, mock_get_member, db):
    mock_get_family.return_value = _make_family()
    mock_get_member.return_value = _make_member(user_id=10, role="member")
    with pytest.raises(ForbiddenError, match="organizer"):
        service.update_member_role(
            db, family_id=1, actor_id=10, target_user_id=20, role="organizer"
        )


@patch(f"{REPO}.count_organizers")
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_update_role_target_not_a_member(mock_get_family, mock_get_member, mock_count, db):
    mock_get_family.return_value = _make_family()
    actor = _make_member(user_id=10, role="organizer")
    mock_get_member.side_effect = [actor, None]
    with pytest.raises(NotFoundError):
        service.update_member_role(
            db, family_id=1, actor_id=10, target_user_id=20, role="organizer"
        )
    mock_count.assert_not_called()


@patch(f"{REPO}.get_family_members_with_users")
@patch(f"{REPO}.update_member_role")
@patch(f"{REPO}.count_organizers")
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_update_role_promote_member_to_organizer(
    mock_get_family, mock_get_member, mock_count, mock_update, mock_get_members, db
):
    family = _make_family(id=1, name="Smith Family", created_by_id=10)
    actor = _make_member(user_id=10, role="organizer")
    target = _make_member(user_id=20, role="member")
    user = _make_user(id=20, name="Bob")
    mock_get_family.return_value = family
    mock_get_member.side_effect = [actor, target]
    mock_get_members.return_value = [(target, user)]

    result = service.update_member_role(
        db, family_id=1, actor_id=10, target_user_id=20, role="organizer"
    )

    mock_update.assert_called_once_with(db, target, "organizer")
    mock_count.assert_not_called()  # promote → guard not evaluated
    assert result["id"] == 1


@patch(f"{REPO}.get_family_members_with_users")
@patch(f"{REPO}.update_member_role")
@patch(f"{REPO}.count_organizers")
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_update_role_promote_already_organizer(
    mock_get_family, mock_get_member, mock_count, mock_update, mock_get_members, db
):
    family = _make_family(id=1)
    actor = _make_member(user_id=10, role="organizer")
    target = _make_member(user_id=20, role="organizer")
    user = _make_user(id=20, name="Bob")
    mock_get_family.return_value = family
    mock_get_member.side_effect = [actor, target]
    mock_get_members.return_value = [(target, user)]

    result = service.update_member_role(
        db, family_id=1, actor_id=10, target_user_id=20, role="organizer"
    )

    mock_update.assert_called_once_with(db, target, "organizer")
    mock_count.assert_not_called()  # promoting → demotion guard not evaluated
    assert result["id"] == 1


@patch(f"{REPO}.get_family_members_with_users")
@patch(f"{REPO}.update_member_role")
@patch(f"{REPO}.count_organizers", return_value=2)
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_update_role_demote_non_last_organizer(
    mock_get_family, mock_get_member, mock_count, mock_update, mock_get_members, db
):
    family = _make_family(id=1)
    actor = _make_member(user_id=10, role="organizer")
    target = _make_member(user_id=20, role="organizer")
    user = _make_user(id=20, name="Bob")
    mock_get_family.return_value = family
    mock_get_member.side_effect = [actor, target]
    mock_get_members.return_value = [(target, user)]

    result = service.update_member_role(
        db, family_id=1, actor_id=10, target_user_id=20, role="member"
    )

    mock_update.assert_called_once_with(db, target, "member")
    assert result["id"] == 1


@patch(f"{REPO}.update_member_role")
@patch(f"{REPO}.count_organizers", return_value=1)
@patch(f"{REPO}.get_family_member")
@patch(f"{REPO}.get_family")
def test_update_role_demote_last_organizer_raises_conflict(
    mock_get_family, mock_get_member, mock_count, mock_update, db
):
    mock_get_family.return_value = _make_family()
    actor = _make_member(user_id=10, role="organizer")
    target = _make_member(user_id=10, role="organizer")  # self-demote, sole organizer
    mock_get_member.side_effect = [actor, target]
    with pytest.raises(ConflictError):
        service.update_member_role(
            db, family_id=1, actor_id=10, target_user_id=10, role="member"
        )
    mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# users_share_family
# ---------------------------------------------------------------------------


def test_users_share_family_overlap_returns_true():
    db = MagicMock()
    # a_id's families = {1, 2}; b_id's families = {2, 3} -> overlap on family 2
    with patch(f"{REPO}.family_ids_for_user", side_effect=[{1, 2}, {2, 3}]):
        assert service.users_share_family(db, 10, 20) is True


def test_users_share_family_disjoint_returns_false():
    db = MagicMock()
    with patch(f"{REPO}.family_ids_for_user", side_effect=[{1, 2}, {3, 4}]):
        assert service.users_share_family(db, 10, 20) is False


def test_users_share_family_no_memberships_returns_false():
    db = MagicMock()
    with patch(f"{REPO}.family_ids_for_user", side_effect=[set(), set()]):
        assert service.users_share_family(db, 10, 20) is False
