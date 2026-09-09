"""Filing resolution and the two derived sets (NEU-1269 §2, §3.1).

The set arithmetic itself is exercised against real rows in
`tests/integration/routers/test_claims.py`; what is unit-tested here is the
decision `resolve_filing` makes once the sets are known, because that is where
the 400, the silent auto-pick and the stale-id forgiveness all diverge.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.claims import service
from app.schemas.claim import CandidateFamily, OccasionCandidate
from app.services.exceptions import BadRequestError, ForbiddenError

SETS = "app.claims.service.occasion_sets"


def _candidate(id, name="Christmas 2026", is_archived=False, family_id=1):
    return OccasionCandidate(
        id=id,
        name=name,
        is_archived=is_archived,
        family=CandidateFamily(id=family_id, name="The Boones"),
    )


def _resolve(occasion_id=None, provided=False):
    return service.resolve_filing(
        MagicMock(), SimpleNamespace(id=1), SimpleNamespace(id=2), occasion_id, provided
    )


# --- no id supplied: the auto-pick and the prompt ---


@patch(SETS, return_value=([], []))
def test_no_id_and_nothing_suggested_files_under_nothing(_sets):
    assert _resolve() is None


@patch(SETS)
def test_no_id_and_one_suggestion_files_silently(mock_sets):
    one = [_candidate(7)]
    mock_sets.return_value = (one, one)
    assert _resolve() == 7


@patch(SETS)
def test_no_id_and_two_suggestions_is_ambiguous(mock_sets):
    two = [_candidate(7), _candidate(8, "Gran's 80th")]
    mock_sets.return_value = (two, two)
    with pytest.raises(BadRequestError) as exc:
        _resolve()
    # The client reads this one, so it is a code rather than a sentence.
    assert str(exc.value) == service.AMBIGUOUS_OCCASION


# --- an id supplied ---


@patch(SETS)
def test_an_allowed_id_is_honoured_exactly(mock_sets):
    archived, active = _candidate(7, is_archived=True), _candidate(8)
    mock_sets.return_value = ([archived, active], [active])
    # Explicitly filing under a past occasion is the whole point of `allowed`
    # staying wide, so this must not be quietly rewritten to the suggestion.
    assert _resolve(occasion_id=7, provided=True) == 7


@patch(SETS)
def test_an_explicit_null_files_under_nothing(mock_sets):
    one = [_candidate(7)]
    mock_sets.return_value = (one, one)
    # An explicit null is a choice, not an omission: it must not auto-pick.
    assert _resolve(occasion_id=None, provided=True) is None


@patch(SETS)
def test_a_stale_id_falls_back_to_the_single_suggestion(mock_sets):
    one = [_candidate(7)]
    mock_sets.return_value = (one, one)
    # Claiming is competitive: a share revoked between read and click must never
    # cost the user the gift (§3.2).
    assert _resolve(occasion_id=999, provided=True) == 7


@patch(SETS, return_value=([], []))
def test_a_stale_id_with_nothing_suggested_files_under_nothing(_sets):
    assert _resolve(occasion_id=999, provided=True) is None


@patch(SETS)
def test_a_stale_id_never_raises_even_when_suggestions_are_ambiguous(mock_sets):
    two = [_candidate(7), _candidate(8, "Gran's 80th")]
    mock_sets.return_value = (two, two)
    # The 400 exists to catch a client that did not prompt. This client *did*
    # prompt — it just sent an id that has since gone stale — so the claim
    # stands, unfiled, and PATCH is the correction path.
    assert _resolve(occasion_id=999, provided=True) is None


# --- the sets themselves ---


@patch("app.claims.service.shares_repo.get_shared_occasions_for_member")
def test_suggested_narrows_to_active(mock_rows):
    family = SimpleNamespace(id=1, name="The Boones")
    mock_rows.return_value = [
        (SimpleNamespace(id=1, name="Christmas 2026", is_archived=True), family),
        (SimpleNamespace(id=2, name="Christmas 2027", is_archived=True), family),
        (SimpleNamespace(id=3, name="Christmas 2028", is_archived=False), family),
    ]
    allowed, suggested = service.occasion_sets(
        MagicMock(), SimpleNamespace(id=1), SimpleNamespace(id=2)
    )
    # Year three: without the narrowing, every claim would prompt forever.
    assert [c.id for c in allowed] == [1, 2, 3]
    assert [c.id for c in suggested] == [3]


@patch("app.claims.service.shares_repo.get_shared_occasions_for_member")
def test_suggested_falls_back_to_all_when_none_are_active(mock_rows):
    family = SimpleNamespace(id=1, name="The Boones")
    mock_rows.return_value = [
        (SimpleNamespace(id=1, name="Christmas 2026", is_archived=True), family),
    ]
    allowed, suggested = service.occasion_sets(
        MagicMock(), SimpleNamespace(id=1), SimpleNamespace(id=2)
    )
    # The January shopper: one archived occasion still yields one suggestion.
    assert [c.id for c in allowed] == [1]
    assert [c.id for c in suggested] == [1]


# --- PATCH guards ---


@patch("app.claims.service.repo.get_claim", return_value=None)
def test_a_missing_claim_is_forbidden_not_missing(_get):
    # A 404 here would tell the list's owner that a claim exists.
    with pytest.raises(ForbiddenError):
        service.get_own_claim(MagicMock(), 1, SimpleNamespace(id=2))


@patch("app.claims.service.repo.get_claim")
def test_someone_elses_claim_is_forbidden(mock_get):
    mock_get.return_value = SimpleNamespace(id=1, user_id=99)
    with pytest.raises(ForbiddenError):
        service.get_own_claim(MagicMock(), 1, SimpleNamespace(id=2))
