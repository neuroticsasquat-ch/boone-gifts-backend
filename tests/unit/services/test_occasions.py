from datetime import datetime, timedelta, timezone
from decimal import Decimal
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
BUDGETS_SERVICE = "app.occasions.service.budgets_service"


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


def _make_occasion(
    id: int = 5, family_id: int = 1, created_by_id: int = 99
) -> MagicMock:
    """`created_by_id` defaults to somebody other than `_make_user()`, so the
    creator arm of the archive gate has to be asked for explicitly."""
    occasion = MagicMock(spec=Occasion)
    occasion.id = id
    occasion.family_id = family_id
    occasion.created_by_id = created_by_id
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


def test_get_occasion_returns_it_with_its_family_for_a_member():
    """The family comes back too — the page's heading names it (NEU-1321), and
    it is the row the membership gate has already loaded, not a second read."""
    db = MagicMock()
    occasion = _make_occasion()
    family = _make_family()
    with patch(FAMILIES_REPO) as families_repo, patch(REPO) as repo:
        repo.get_occasion.return_value = occasion
        families_repo.get_family.return_value = family
        families_repo.get_family_member.return_value = _make_member("member")

        assert service.get_occasion(db, occasion_id=5, actor=_make_user()) == (
            occasion,
            family,
        )

    families_repo.get_family.assert_called_once_with(db, occasion.family_id)


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
# update_occasion — per field: organizer renames, organizer-or-creator archives
# ---------------------------------------------------------------------------


def _update(db, occasion, role, update_data, actor=None, family_member=True):
    """Run `update_occasion` with the membership gate stubbed to `role`.

    The gate resolves `families_repo` in *this* service's namespace since
    NEU-1294 — the role check is inline rather than borrowed from
    `_require_organizer`, because the rule is now per field rather than per
    endpoint and only the `name` half is organizer-only.
    """
    with patch(FAMILIES_REPO) as families_repo, patch(REPO) as repo:
        repo.get_occasion.return_value = occasion
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = (
            _make_member(role) if family_member else None
        )
        repo.update_occasion.return_value = occasion
        try:
            return (
                service.update_occasion(
                    db,
                    occasion_id=5,
                    actor=actor or _make_user(),
                    update_data=update_data,
                ),
                repo,
            )
        except (ForbiddenError, NotFoundError):
            repo.update_occasion.assert_not_called()
            raise


def test_an_organizer_may_rename_an_occasion():
    db = MagicMock()
    occasion = _make_occasion()

    result, repo = _update(db, occasion, "organizer", {"name": "Renamed"})

    assert result is occasion
    repo.update_occasion.assert_called_once_with(db, occasion, {"name": "Renamed"})


def test_a_plain_member_may_not_rename_an_occasion():
    with pytest.raises(ForbiddenError):
        _update(MagicMock(), _make_occasion(), "member", {"name": "Renamed"})


def test_an_outsider_may_not_update_an_occasion():
    with pytest.raises(ForbiddenError):
        _update(
            MagicMock(),
            _make_occasion(),
            "member",
            {"name": "Renamed"},
            family_member=False,
        )


def test_the_creator_may_archive_an_occasion_they_do_not_organize():
    """The correctness fix the audience rule forces: a member who created an
    occasion is nudged to archive it, so they must be able to."""
    db = MagicMock()
    actor = _make_user()
    occasion = _make_occasion(created_by_id=actor.id)

    result, repo = _update(
        db, occasion, "member", {"is_archived": True}, actor=actor
    )

    assert result is occasion
    repo.update_occasion.assert_called_once_with(db, occasion, {"is_archived": True})


def test_the_creator_may_unarchive_too():
    """The gate is on the field, not the direction — a creator who closed an
    occasion by mistake can reopen it."""
    db = MagicMock()
    actor = _make_user()
    occasion = _make_occasion(created_by_id=actor.id)

    _, repo = _update(db, occasion, "member", {"is_archived": False}, actor=actor)

    repo.update_occasion.assert_called_once_with(db, occasion, {"is_archived": False})


def test_a_member_who_did_not_create_it_may_not_archive_it():
    with pytest.raises(ForbiddenError):
        _update(MagicMock(), _make_occasion(), "member", {"is_archived": True})


def test_the_creator_still_may_not_rename_it():
    """Archiving is reversible and withdraws nothing; a rename changes a label
    everyone sees and every budget is filed under."""
    actor = _make_user()
    with pytest.raises(ForbiddenError):
        _update(
            MagicMock(),
            _make_occasion(created_by_id=actor.id),
            "member",
            {"name": "Renamed"},
            actor=actor,
        )


def test_renaming_and_archiving_at_once_needs_the_organizer_role():
    """The request contains a rename, so it carries the rename's gate."""
    actor = _make_user()
    with pytest.raises(ForbiddenError):
        _update(
            MagicMock(),
            _make_occasion(created_by_id=actor.id),
            "member",
            {"name": "Renamed", "is_archived": True},
            actor=actor,
        )


def test_an_outsider_may_not_no_op_an_occasion_they_cannot_see():
    """An empty update still needs membership: answering 200 would confirm the
    occasion exists to somebody with no business knowing."""
    with pytest.raises(ForbiddenError):
        _update(MagicMock(), _make_occasion(), "member", {}, family_member=False)


def test_update_occasion_raises_not_found_for_an_unknown_id():
    db = MagicMock()
    with patch(REPO) as repo:
        repo.get_occasion.return_value = None
        with pytest.raises(NotFoundError):
            service.update_occasion(
                db, occasion_id=5, actor=_make_user(), update_data={"name": "Renamed"}
            )


@patch(BUDGETS_SERVICE)
@patch("app.occasions.service.claims_repo.get_shopping_for_occasion")
def test_shopping_is_scoped_to_the_caller(mock_shopping, budgets_service):
    """The actor's own id is what bounds both halves of the payload — there is
    no parameter that could widen either to another member's claims."""
    db = MagicMock()
    mock_shopping.return_value = [{"name": "Skillet"}]
    budgets_service.get_rollup.return_value = {"amount": None}
    actor = _make_user(id=10)

    with patch(REPO) as repo, patch(FAMILIES_REPO) as families_repo:
        repo.get_occasion.return_value = _make_occasion()
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = _make_member("member")

        result = service.list_shopping(db, occasion_id=5, actor=actor)

    mock_shopping.assert_called_once_with(db, 5, 10)
    budgets_service.get_rollup.assert_called_once_with(db, user_id=10, occasion_id=5)
    assert result == {"budget": {"amount": None}, "items": [{"name": "Skillet"}]}


@patch(BUDGETS_SERVICE)
def test_set_budget_is_the_callers_own_and_needs_only_membership(budgets_service):
    """An organizer has no more say over money than any other member: the gate
    is membership, and the budget written is always the caller's own."""
    db = MagicMock()
    budgets_service.set_budget.return_value = {"amount": Decimal("200.00")}
    actor = _make_user(id=10)

    with patch(REPO) as repo, patch(FAMILIES_REPO) as families_repo:
        repo.get_occasion.return_value = _make_occasion()
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = _make_member("member")

        result = service.set_budget(
            db, occasion_id=5, actor=actor, amount=Decimal("200.00")
        )

    budgets_service.set_budget.assert_called_once_with(
        db, user_id=10, occasion_id=5, amount=Decimal("200.00")
    )
    assert result == {"amount": Decimal("200.00")}


@patch(BUDGETS_SERVICE)
def test_set_budget_refuses_a_non_member(budgets_service):
    db = MagicMock()
    with patch(REPO) as repo, patch(FAMILIES_REPO) as families_repo:
        repo.get_occasion.return_value = _make_occasion()
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = None

        with pytest.raises(ForbiddenError):
            service.set_budget(
                db, occasion_id=5, actor=_make_user(), amount=Decimal("200.00")
            )

    budgets_service.set_budget.assert_not_called()


@patch(BUDGETS_SERVICE)
def test_clear_budget_refuses_a_non_member(budgets_service):
    db = MagicMock()
    with patch(REPO) as repo, patch(FAMILIES_REPO) as families_repo:
        repo.get_occasion.return_value = _make_occasion()
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = None

        with pytest.raises(ForbiddenError):
            service.clear_budget(db, occasion_id=5, actor=_make_user())

    budgets_service.clear_budget.assert_not_called()


def test_shopping_refuses_a_non_member():
    db = MagicMock()
    with patch(REPO) as repo, patch(FAMILIES_REPO) as families_repo:
        repo.get_occasion.return_value = _make_occasion()
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = None

        with pytest.raises(ForbiddenError):
            service.list_shopping(db, occasion_id=5, actor=_make_user())


def test_shopping_raises_not_found_for_an_unknown_occasion():
    db = MagicMock()
    with patch(REPO) as repo:
        repo.get_occasion.return_value = None
        with pytest.raises(NotFoundError):
            service.list_shopping(db, occasion_id=5, actor=_make_user())


def test_list_all_occasions_passes_the_callers_own_id_and_nothing_else():
    """The index has no membership gate on purpose: the query is scoped by the
    caller's memberships, so an occasion they cannot see is a row that never
    exists rather than one that gets filtered out. What this pins is the other
    half — the only user id reaching the repository is the caller's."""
    db = MagicMock()
    with patch(REPO) as repo:
        result = service.list_all_occasions(
            db, actor=_make_user(id=10), archived=False
        )

    repo.get_occasion_summaries.assert_called_once_with(
        db, user_id=10, archived=False
    )
    assert result is repo.get_occasion_summaries.return_value


def test_list_all_occasions_threads_the_archived_flag_through():
    db = MagicMock()
    with patch(REPO) as repo:
        service.list_all_occasions(db, actor=_make_user(id=10), archived=True)

    assert repo.get_occasion_summaries.call_args.kwargs["archived"] is True


# ---------------------------------------------------------------------------
# The archive nudge (NEU-1294)
# ---------------------------------------------------------------------------


def test_list_archive_prompts_passes_the_callers_own_id_and_the_rule():
    """No family, no user, no filter — the caller's own memberships are the
    whole scope, so there is no argument that could widen it to anyone else's
    prompts (`CONTEXT.md` invariant 1)."""
    db = MagicMock()
    with patch(REPO) as repo:
        repo.get_archive_prompts.return_value = []

        service.list_archive_prompts(db, actor=_make_user())

    repo.get_archive_prompts.assert_called_once_with(
        db, user_id=10, idle_days=service.ARCHIVE_PROMPT_IDLE_DAYS
    )


def test_the_idle_and_snooze_periods_are_the_spec_ones():
    """Product rules, not deployment knobs: a per-environment threshold would
    make the dev seed's stale fixture depend on config."""
    assert service.ARCHIVE_PROMPT_IDLE_DAYS == 60
    assert service.ARCHIVE_PROMPT_SNOOZE_DAYS == 30


def _dismiss(db, occasion, role, actor=None, family_member=True):
    with patch(FAMILIES_REPO) as families_repo, patch(REPO) as repo:
        repo.get_occasion.return_value = occasion
        families_repo.get_family.return_value = _make_family()
        families_repo.get_family_member.return_value = (
            _make_member(role) if family_member else None
        )
        try:
            service.dismiss_archive_prompt(
                db, occasion_id=5, actor=actor or _make_user()
            )
            return repo
        except (ForbiddenError, NotFoundError):
            repo.upsert_dismissal.assert_not_called()
            raise


def test_an_organizer_may_dismiss_and_the_snooze_is_the_servers_rule():
    db = MagicMock()
    occasion = _make_occasion()
    before = datetime.now(timezone.utc)

    repo = _dismiss(db, occasion, "organizer")

    repo.upsert_dismissal.assert_called_once()
    kwargs = repo.upsert_dismissal.call_args.kwargs
    assert kwargs["user_id"] == 10
    assert kwargs["occasion_id"] == 5
    # 30 days out, bracketed rather than pinned: the service reads the clock
    # itself, which is the point — the endpoint takes no body.
    assert (
        before + timedelta(days=service.ARCHIVE_PROMPT_SNOOZE_DAYS)
        <= kwargs["dismissed_until"]
        <= datetime.now(timezone.utc)
        + timedelta(days=service.ARCHIVE_PROMPT_SNOOZE_DAYS)
    )


def test_the_creator_may_dismiss_without_organizing():
    """The dismissal's audience is the nudge's audience — anyone who can be
    asked the question can answer "not yet"."""
    actor = _make_user()

    repo = _dismiss(
        MagicMock(), _make_occasion(created_by_id=actor.id), "member", actor=actor
    )

    repo.upsert_dismissal.assert_called_once()


def test_a_member_outside_the_audience_may_not_dismiss():
    with pytest.raises(ForbiddenError):
        _dismiss(MagicMock(), _make_occasion(), "member")


def test_an_outsider_may_not_dismiss():
    with pytest.raises(ForbiddenError):
        _dismiss(MagicMock(), _make_occasion(), "member", family_member=False)


def test_dismissing_an_unknown_occasion_is_not_found():
    db = MagicMock()
    with patch(REPO) as repo:
        repo.get_occasion.return_value = None
        with pytest.raises(NotFoundError):
            service.dismiss_archive_prompt(db, occasion_id=5, actor=_make_user())
        repo.upsert_dismissal.assert_not_called()


def test_dismissal_does_not_re_check_staleness():
    """The race is ordinary — the banner renders, somebody shares in, and only
    then does the user press Not yet. Refusing that call would fail a button
    that was on screen, so the service asks the repository nothing about the
    occasion's age.
    """
    db = MagicMock()

    repo = _dismiss(db, _make_occasion(), "organizer")

    repo.get_archive_prompts.assert_not_called()
