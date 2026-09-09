"""Budgets — the endpoints, the rollup, and who can see whose money (NEU-1275).

Every budget is private to the user who set it. The tests that matter most here
are the ones proving that: a second member of the same family, filing claims
under the same occasion, changes nothing about what the caller reads.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.dependencies import create_access_token
from app.models.claim import Claim
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.occasion import Occasion
from app.models.user import User


@pytest.fixture
def family(db, member_user):
    fam = Family(name="Boone Family", created_by_id=member_user.id)
    db.add(fam)
    db.flush()
    db.add(FamilyMember(family_id=fam.id, user_id=member_user.id, role="organizer"))
    db.flush()
    return fam


@pytest.fixture
def occasion(db, family, member_user):
    occ = Occasion(
        family_id=family.id, name="Christmas 2026", created_by_id=member_user.id
    )
    db.add(occ)
    db.flush()
    return occ


@pytest.fixture
def other_member(db, family):
    user = User(email="other@test.com", name="Other", role="member", password_hash="x")
    user.set_password("x")
    db.add(user)
    db.flush()
    db.add(FamilyMember(family_id=family.id, user_id=user.id, role="member"))
    db.flush()
    return user


@pytest.fixture
def other_member_headers(other_member):
    return {"Authorization": f"Bearer {create_access_token(other_member)}"}


@pytest.fixture
def gift_list(db, other_member):
    gl = GiftList(name="Gran's List", owner_id=other_member.id)
    db.add(gl)
    db.flush()
    return gl


def _claim(
    db, gift_list, claimer, name, occasion=None, purchased_at=None, amount_paid=None
):
    gift = Gift(list_id=gift_list.id, name=name)
    db.add(gift)
    db.flush()
    claim = Claim(
        gift_id=gift.id,
        user_id=claimer.id,
        occasion_id=occasion.id if occasion is not None else None,
        claimed_at=datetime.now(timezone.utc),
        purchased_at=purchased_at,
        amount_paid=amount_paid,
    )
    db.add(claim)
    db.flush()
    return claim


BOUGHT = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# PUT / DELETE /occasions/{id}/budget
# ---------------------------------------------------------------------------


def test_put_sets_the_budget_and_returns_the_rollup(
    client, member_headers, occasion
):
    response = client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "200.00"},
        headers=member_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "amount": "200.00",
        "spent": "0.00",
        "remaining": "200.00",
        "bought_count": 0,
        "total_count": 0,
        "unpriced_count": 0,
    }


def test_put_replaces_the_existing_budget(client, member_headers, occasion):
    """One budget per (user, occasion) — the second write moves the target
    rather than adding a second one."""
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "200.00"},
        headers=member_headers,
    )

    response = client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "250.00"},
        headers=member_headers,
    )

    assert response.json()["amount"] == "250.00"
    assert (
        client.get(
            f"/occasions/{occasion.id}/shopping", headers=member_headers
        ).json()["budget"]["amount"]
        == "250.00"
    )


def test_delete_clears_the_target_and_keeps_the_counts(
    client, db, member_user, member_headers, occasion, gift_list
):
    _claim(
        db,
        gift_list,
        member_user,
        "Puzzle",
        occasion=occasion,
        purchased_at=BOUGHT,
        amount_paid=Decimal("18.00"),
    )
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "200.00"},
        headers=member_headers,
    )

    response = client.delete(
        f"/occasions/{occasion.id}/budget", headers=member_headers
    )

    assert response.status_code == 200
    # Clearing a target is not unclaiming anything: the spend survives it.
    assert response.json() == {
        "amount": None,
        "spent": "18.00",
        "remaining": None,
        "bought_count": 1,
        "total_count": 1,
        "unpriced_count": 0,
    }


def test_delete_is_404_when_no_budget_is_set(client, member_headers, occasion):
    response = client.delete(
        f"/occasions/{occasion.id}/budget", headers=member_headers
    )

    assert response.status_code == 404


def test_a_negative_budget_is_refused(client, member_headers, occasion):
    response = client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "-1.00"},
        headers=member_headers,
    )

    assert response.status_code == 422


def test_budget_endpoints_require_membership(
    client, admin_headers, occasion
):
    """Same gate as the occasion's other reads: a non-member learns nothing,
    not even what the budget line would say."""
    assert (
        client.put(
            f"/occasions/{occasion.id}/budget",
            json={"amount": "10.00"},
            headers=admin_headers,
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/occasions/{occasion.id}/budget", headers=admin_headers
        ).status_code
        == 403
    )


def test_budget_endpoints_404_for_an_unknown_occasion(client, member_headers):
    assert (
        client.put(
            "/occasions/999999/budget",
            json={"amount": "10.00"},
            headers=member_headers,
        ).status_code
        == 404
    )
    assert client.delete("/occasions/999999/budget").status_code == 401


def test_budget_endpoints_require_authentication(client, occasion):
    assert (
        client.put(
            f"/occasions/{occasion.id}/budget", json={"amount": "10.00"}
        ).status_code
        == 401
    )
    assert client.delete(f"/occasions/{occasion.id}/budget").status_code == 401


# ---------------------------------------------------------------------------
# The rollup, and what it deliberately does not count
# ---------------------------------------------------------------------------


def test_rollup_counts_bought_but_never_guesses_at_an_unrecorded_amount(
    client, db, member_user, member_headers, occasion, gift_list
):
    """The one arithmetic rule the budget line rests on: a purchase with no
    amount recorded is bought, is reported as unpriced, and is never money."""
    _claim(
        db, gift_list, member_user, "Shoes",
        occasion=occasion, purchased_at=BOUGHT, amount_paid=Decimal("85.00"),
    )
    _claim(
        db, gift_list, member_user, "Puzzle",
        occasion=occasion, purchased_at=BOUGHT, amount_paid=Decimal("18.00"),
    )
    _claim(
        db, gift_list, member_user, "Socks", occasion=occasion, purchased_at=BOUGHT
    )
    _claim(
        db, gift_list, member_user, "Book", occasion=occasion, purchased_at=BOUGHT
    )
    _claim(db, gift_list, member_user, "Skillet", occasion=occasion)
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "200.00"},
        headers=member_headers,
    )

    budget = client.get(
        f"/occasions/{occasion.id}/shopping", headers=member_headers
    ).json()["budget"]

    assert budget["spent"] == "103.00"
    assert budget["remaining"] == "97.00"
    assert budget["bought_count"] == 4
    assert budget["total_count"] == 5
    assert budget["unpriced_count"] == 2


def test_an_amount_survives_unticking_and_stays_in_the_spend(
    client, db, member_user, member_headers, occasion, gift_list
):
    """`spent` counts recorded money; the counts describe shopping.

    Unticking keeps `amount_paid` so re-ticking need not retype it
    (`app/gifts/service.py:unpurchase_gift`), and that money stays in the
    total: it left the claimer's pocket either way, and dropping it silently —
    with no `unpriced_count` to disclose the gap — is the one failure a budget
    line must not have. `bought_count` is what moves.
    """
    claim = _claim(
        db, gift_list, member_user, "Shoes",
        occasion=occasion, purchased_at=BOUGHT, amount_paid=Decimal("85.00"),
    )
    claim.purchased_at = None
    db.flush()

    budget = client.get(
        f"/occasions/{occasion.id}/shopping", headers=member_headers
    ).json()["budget"]

    assert budget["spent"] == "85.00"
    assert budget["bought_count"] == 0
    assert budget["unpriced_count"] == 0
    assert budget["total_count"] == 1


def test_rollup_reports_an_overspend_rather_than_hiding_it(
    client, db, member_user, member_headers, occasion, gift_list
):
    """A budget is a target, not a limit."""
    _claim(
        db, gift_list, member_user, "Shoes",
        occasion=occasion, purchased_at=BOUGHT, amount_paid=Decimal("85.00"),
    )
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "50.00"},
        headers=member_headers,
    )

    budget = client.get(
        f"/occasions/{occasion.id}/shopping", headers=member_headers
    ).json()["budget"]

    assert budget["remaining"] == "-35.00"


def test_shopping_carries_a_null_target_when_no_budget_is_set(
    client, db, member_user, member_headers, occasion, gift_list
):
    _claim(db, gift_list, member_user, "Skillet", occasion=occasion)

    budget = client.get(
        f"/occasions/{occasion.id}/shopping", headers=member_headers
    ).json()["budget"]

    assert budget["amount"] is None
    assert budget["remaining"] is None
    assert budget["total_count"] == 1


def test_rollup_counts_only_claims_filed_under_this_occasion(
    client, db, member_user, member_headers, family, occasion, gift_list
):
    other_occasion = Occasion(
        family_id=family.id, name="Gran's 80th", created_by_id=member_user.id
    )
    db.add(other_occasion)
    db.flush()
    _claim(
        db, gift_list, member_user, "Filed here",
        occasion=occasion, purchased_at=BOUGHT, amount_paid=Decimal("10.00"),
    )
    _claim(
        db, gift_list, member_user, "Filed elsewhere",
        occasion=other_occasion, purchased_at=BOUGHT, amount_paid=Decimal("99.00"),
    )
    _claim(
        db, gift_list, member_user, "Filed nowhere",
        purchased_at=BOUGHT, amount_paid=Decimal("99.00"),
    )

    budget = client.get(
        f"/occasions/{occasion.id}/shopping", headers=member_headers
    ).json()["budget"]

    assert budget["spent"] == "10.00"
    assert budget["total_count"] == 1


# ---------------------------------------------------------------------------
# Invariant 1: no endpoint returns another user's budget, spend or counts
# ---------------------------------------------------------------------------


def test_no_endpoint_returns_another_users_budget_or_spend(
    client,
    db,
    member_user,
    member_headers,
    other_member,
    other_member_headers,
    occasion,
    gift_list,
):
    """Two members of one family, budgeting and spending against the same
    occasion. Neither reads a number belonging to the other — and there is no
    parameter, admin path or aggregate anywhere that would let them.
    """
    _claim(
        db, gift_list, member_user, "Mine",
        occasion=occasion, purchased_at=BOUGHT, amount_paid=Decimal("18.00"),
    )
    _claim(
        db, gift_list, other_member, "Theirs",
        occasion=occasion, purchased_at=BOUGHT, amount_paid=Decimal("500.00"),
    )
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "200.00"},
        headers=member_headers,
    )
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "1000.00"},
        headers=other_member_headers,
    )

    mine = client.get(
        f"/occasions/{occasion.id}/shopping", headers=member_headers
    ).json()
    theirs = client.get(
        f"/occasions/{occasion.id}/shopping", headers=other_member_headers
    ).json()

    assert mine["budget"] == {
        "amount": "200.00",
        "spent": "18.00",
        "remaining": "182.00",
        "bought_count": 1,
        "total_count": 1,
        "unpriced_count": 0,
    }
    assert theirs["budget"]["amount"] == "1000.00"
    assert theirs["budget"]["spent"] == "500.00"
    assert [row["name"] for row in mine["items"]] == ["Mine"]


def test_clearing_one_members_budget_leaves_the_others_standing(
    client, member_headers, other_member_headers, occasion
):
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "200.00"},
        headers=member_headers,
    )
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "1000.00"},
        headers=other_member_headers,
    )

    client.delete(f"/occasions/{occasion.id}/budget", headers=member_headers)

    assert (
        client.get(
            f"/occasions/{occasion.id}/shopping", headers=other_member_headers
        ).json()["budget"]["amount"]
        == "1000.00"
    )


# ---------------------------------------------------------------------------
# PUT / DELETE /folders/{id}/budget
# ---------------------------------------------------------------------------


def test_folder_budget_counts_claims_on_the_folders_lists(
    client, db, member_user, member_headers, folder, folder_item, sample_list
):
    _claim(
        db, sample_list, member_user, "In the folder",
        purchased_at=BOUGHT, amount_paid=Decimal("31.50"),
    )
    elsewhere = GiftList(name="Not in the folder", owner_id=member_user.id)
    db.add(elsewhere)
    db.flush()
    _claim(
        db, elsewhere, member_user, "Outside",
        purchased_at=BOUGHT, amount_paid=Decimal("99.00"),
    )

    response = client.put(
        f"/folders/{folder.id}/budget",
        json={"amount": "50.00"},
        headers=member_headers,
    )

    assert response.json() == {
        "amount": "50.00",
        "spent": "31.50",
        "remaining": "18.50",
        "bought_count": 1,
        "total_count": 1,
        "unpriced_count": 0,
    }


def test_folder_budget_is_returned_with_the_shopping_payload(
    client, member_headers, folder
):
    client.put(
        f"/folders/{folder.id}/budget",
        json={"amount": "50.00"},
        headers=member_headers,
    )

    payload = client.get(
        f"/folders/{folder.id}/shopping", headers=member_headers
    ).json()

    assert payload["budget"]["amount"] == "50.00"
    assert payload["items"] == []


def test_folder_budget_is_owner_only(client, admin_headers, folder):
    assert (
        client.put(
            f"/folders/{folder.id}/budget",
            json={"amount": "50.00"},
            headers=admin_headers,
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/folders/{folder.id}/budget", headers=admin_headers
        ).status_code
        == 403
    )


def test_folder_delete_is_404_when_no_budget_is_set(
    client, member_headers, folder
):
    assert (
        client.delete(
            f"/folders/{folder.id}/budget", headers=member_headers
        ).status_code
        == 404
    )


def test_a_folder_budget_and_an_occasion_budget_are_separate(
    client, db, member_user, member_headers, occasion, folder, folder_item, sample_list
):
    """One user, two scopes, one amount each. The unique constraints are per
    scope, and a NULL never collides, so neither write disturbs the other."""
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "200.00"},
        headers=member_headers,
    )
    client.put(
        f"/folders/{folder.id}/budget",
        json={"amount": "50.00"},
        headers=member_headers,
    )

    assert (
        client.get(
            f"/occasions/{occasion.id}/shopping", headers=member_headers
        ).json()["budget"]["amount"]
        == "200.00"
    )
    assert (
        client.get(
            f"/folders/{folder.id}/shopping", headers=member_headers
        ).json()["budget"]["amount"]
        == "50.00"
    )


def test_deleting_a_folder_takes_its_budget_with_it(
    client, member_headers, folder
):
    """`budgets.folder_id` is a real foreign key under `PRAGMA foreign_keys=ON`,
    so a budget left behind would make the delete fail outright."""
    client.put(
        f"/folders/{folder.id}/budget",
        json={"amount": "50.00"},
        headers=member_headers,
    )

    assert (
        client.delete(f"/folders/{folder.id}", headers=member_headers).status_code
        == 204
    )


# ---------------------------------------------------------------------------
# Teardown: a budget's scope going away
# ---------------------------------------------------------------------------


def test_deleting_a_family_takes_every_budget_on_its_occasions(
    client, member_headers, other_member_headers, family, occasion
):
    """Budgets point at the occasions, which point at the family, so they
    unwind in that order — the foreign key would refuse the delete otherwise.
    Unlike a claim, a budget has nothing to survive for once its occasion is
    gone: it is a target for shopping that can no longer be filed anywhere.
    """
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "200.00"},
        headers=member_headers,
    )
    client.put(
        f"/occasions/{occasion.id}/budget",
        json={"amount": "1000.00"},
        headers=other_member_headers,
    )

    assert (
        client.delete(f"/families/{family.id}", headers=member_headers).status_code
        == 204
    )


def test_purging_a_user_takes_their_folder_budget_with_them(
    client, admin_headers, member_headers, member_user, folder
):
    """The budget goes before the folder it points at, not after.

    `delete_budgets_by_user` clears both scopes at once, but only the folder
    one can be exercised end to end here: purging a user who *created* an
    occasion already fails on `occasions.created_by_id`, which predates this
    ticket and is not budget-shaped.
    """
    client.put(
        f"/folders/{folder.id}/budget",
        json={"amount": "50.00"},
        headers=member_headers,
    )

    response = client.delete(
        f"/users/{member_user.id}?purge=true", headers=admin_headers
    )

    assert response.status_code == 204
