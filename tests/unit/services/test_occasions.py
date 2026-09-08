from unittest.mock import MagicMock, patch

import pytest

from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.occasion import Occasion
from app.models.user import User
from app.occasions import service
from app.services.exceptions import ForbiddenError, NotFoundError

REPO = "app.occasions.service.repo"
FAMILIES_REPO = "app.occasions.service.families_repo"
# `_require_organizer` is reused from the invites module, so the role gate
# resolves `families_repo` in *that* namespace, not this service's.
ORGANIZER_GATE_REPO = "app.family_invites.service.families_repo"


def _make_user(id: int = 10) -> MagicMock:
    user = MagicMock(spec=User)
    user.id = id
    return user


def _make_member(role: str = "organizer") -> MagicMock:
    member = MagicMock(spec=FamilyMember)
    member.role = role
    return member


def _make_family(id: int = 1) -> MagicMock:
    family = MagicMock(spec=Family)
    family.id = id
    return family


def _make_occasion(id: int = 5, family_id: int = 1) -> MagicMock:
    occasion = MagicMock(spec=Occasion)
    occasion.id = id
    occasion.family_id = family_id
    return occasion


# ---------------------------------------------------------------------------
# Membership gate — shared by list, create and read
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda db, actor: service.list_occasions(
            db, family_id=1, actor=actor, archived=False
        ),
        lambda db, actor: service.create_occasion(
            db, family_id=1, actor=actor, name="Christmas 2026"
        ),
    ],
)
def test_unknown_family_raises_not_found(call):
    db = MagicMock()
    with patch(FAMILIES_REPO) as families_repo:
        families_repo.get_family.return_value = None
        with pytest.raises(NotFoundError):
            call(db, _make_user())


@pytest.mark.parametrize(
    "call",
    [
        lambda db, actor: service.list_occasions(
            db, family_id=1, actor=actor, archived=False
        ),
        lambda db, actor: service.create_occasion(
            db, family_id=1, actor=actor, name="Christmas 2026"
        ),
    ],
)
def test_a_non_member_is_forbidden(call):
    db = MagicMock()
    with patch(FAMILIES_REPO) as families_repo:
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = None
        with pytest.raises(ForbiddenError):
            call(db, _make_user())


# ---------------------------------------------------------------------------
# list_occasions
# ---------------------------------------------------------------------------


def test_list_occasions_passes_the_archived_filter_through():
    db = MagicMock()
    with patch(FAMILIES_REPO) as families_repo, patch(REPO) as repo:
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = _make_member("member")
        repo.get_occasions_for_family.return_value = []

        service.list_occasions(db, family_id=1, actor=_make_user(), archived=True)

    repo.get_occasions_for_family.assert_called_once_with(db, 1, archived=True)


# ---------------------------------------------------------------------------
# create_occasion
# ---------------------------------------------------------------------------


def test_a_plain_member_may_create_an_occasion():
    db = MagicMock()
    occasion = _make_occasion()
    with patch(FAMILIES_REPO) as families_repo, patch(REPO) as repo:
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = _make_member("member")
        repo.has_active_occasion.return_value = False
        repo.create_occasion.return_value = occasion

        created, has_other_active = service.create_occasion(
            db, family_id=1, actor=_make_user(), name="Christmas 2026"
        )

    assert created is occasion
    assert has_other_active is False
    repo.create_occasion.assert_called_once_with(
        db, family_id=1, name="Christmas 2026", created_by_id=10
    )


def test_a_second_active_occasion_is_flagged_not_refused():
    db = MagicMock()
    with patch(FAMILIES_REPO) as families_repo, patch(REPO) as repo:
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = _make_member("member")
        repo.has_active_occasion.return_value = True
        repo.create_occasion.return_value = _make_occasion()

        _, has_other_active = service.create_occasion(
            db, family_id=1, actor=_make_user(), name="Gran's 80th"
        )

    assert has_other_active is True
    repo.create_occasion.assert_called_once()


def test_has_other_active_is_read_before_the_new_row_exists():
    """Otherwise the occasion just created would count as the "other" one."""
    db = MagicMock()
    calls = []
    with patch(FAMILIES_REPO) as families_repo, patch(REPO) as repo:
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = _make_member("member")
        repo.has_active_occasion.side_effect = lambda *a, **k: calls.append(
            "check"
        ) or False
        repo.create_occasion.side_effect = lambda *a, **k: calls.append(
            "create"
        ) or _make_occasion()

        service.create_occasion(
            db, family_id=1, actor=_make_user(), name="Christmas 2026"
        )

    assert calls == ["check", "create"]


# ---------------------------------------------------------------------------
# get_occasion
# ---------------------------------------------------------------------------


def test_get_occasion_returns_it_for_a_member():
    db = MagicMock()
    occasion = _make_occasion()
    with patch(FAMILIES_REPO) as families_repo, patch(REPO) as repo:
        repo.get_occasion.return_value = occasion
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = _make_member("member")

        assert service.get_occasion(db, occasion_id=5, actor=_make_user()) is occasion


def test_get_occasion_raises_not_found_for_an_unknown_id():
    db = MagicMock()
    with patch(REPO) as repo:
        repo.get_occasion.return_value = None
        with pytest.raises(NotFoundError):
            service.get_occasion(db, occasion_id=5, actor=_make_user())


def test_get_occasion_is_forbidden_for_an_outsider():
    db = MagicMock()
    with patch(FAMILIES_REPO) as families_repo, patch(REPO) as repo:
        repo.get_occasion.return_value = _make_occasion()
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = None

        with pytest.raises(ForbiddenError):
            service.get_occasion(db, occasion_id=5, actor=_make_user())


# ---------------------------------------------------------------------------
# update_occasion — organizer only
# ---------------------------------------------------------------------------


def test_an_organizer_may_update_an_occasion():
    db = MagicMock()
    occasion = _make_occasion()
    with patch(ORGANIZER_GATE_REPO) as families_repo, patch(REPO) as repo:
        repo.get_occasion.return_value = occasion
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = _make_member("organizer")
        repo.update_occasion.return_value = occasion

        result = service.update_occasion(
            db, occasion_id=5, actor=_make_user(), update_data={"name": "Renamed"}
        )

    assert result is occasion
    repo.update_occasion.assert_called_once_with(db, occasion, {"name": "Renamed"})


def test_a_plain_member_may_not_update_an_occasion():
    db = MagicMock()
    with patch(ORGANIZER_GATE_REPO) as families_repo, patch(REPO) as repo:
        repo.get_occasion.return_value = _make_occasion()
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = _make_member("member")

        with pytest.raises(ForbiddenError):
            service.update_occasion(
                db, occasion_id=5, actor=_make_user(), update_data={"name": "Renamed"}
            )

    repo.update_occasion.assert_not_called()


def test_an_outsider_may_not_update_an_occasion():
    db = MagicMock()
    with patch(ORGANIZER_GATE_REPO) as families_repo, patch(REPO) as repo:
        repo.get_occasion.return_value = _make_occasion()
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = None

        with pytest.raises(ForbiddenError):
            service.update_occasion(
                db, occasion_id=5, actor=_make_user(), update_data={"name": "Renamed"}
            )

    repo.update_occasion.assert_not_called()


def test_update_occasion_raises_not_found_for_an_unknown_id():
    db = MagicMock()
    with patch(REPO) as repo:
        repo.get_occasion.return_value = None
        with pytest.raises(NotFoundError):
            service.update_occasion(
                db, occasion_id=5, actor=_make_user(), update_data={"name": "Renamed"}
            )
