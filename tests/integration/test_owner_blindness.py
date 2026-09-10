"""Regression guards: no owner-facing response carries claim state (NEU-1268).

`CONTEXT.md` invariant 1 says a list's owner never sees what has been claimed on
it. That used to be serializer discipline — `GiftOwnerRead` omitted three
columns that `GiftRead` included — and it had already failed once: `claimed_count`
was computed for every row `GET /lists` returned, owned ones included, since the
endpoint was written. Nothing rendered it, so nobody noticed.

ADR 0003 made the rule structural by moving the claim off the gift row. These
tests are the belt to that braces, and they are deliberately written as a sweep
over the whole payload rather than as assertions about named fields: a guard
that only knows today's field names cannot catch tomorrow's leak.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.claim import Claim
from app.models.gift import Gift

# Every key that says something about a claim. A response an owner reads must
# not contain any of them, at any depth.
CLAIM_KEYS = {
    "claim",
    "claims",
    "claimed_at",
    "claimed_by_id",
    "claimed_count",
    "my_unpurchased_claim_count",
    "amount_paid",
    "purchased_at",
}


def _keys(payload) -> set[str]:
    """Every key appearing anywhere in a JSON response."""
    if isinstance(payload, dict):
        found = set(payload)
        for value in payload.values():
            found |= _keys(value)
        return found
    if isinstance(payload, list):
        found = set()
        for item in payload:
            found |= _keys(item)
        return found
    return set()


def _assert_blind(payload) -> None:
    leaked = _keys(payload) & CLAIM_KEYS
    assert not leaked, f"owner-facing response leaked claim state: {sorted(leaked)}"


@pytest.fixture
def owned_list_with_a_claim(db, member_user, admin_user, shared_list):
    """A list the member owns, shared with the admin, who has claimed one of its
    two gifts and recorded what they paid for it."""
    claimed = Gift(list_id=shared_list.id, name="Claimed", price=Decimal("39.00"))
    unclaimed = Gift(list_id=shared_list.id, name="Unclaimed")
    db.add_all([claimed, unclaimed])
    db.flush()
    db.add(
        Claim(
            gift_id=claimed.id,
            user_id=admin_user.id,
            claimed_at=datetime.now(timezone.utc),
            purchased_at=datetime.now(timezone.utc),
            amount_paid=Decimal("31.50"),
        )
    )
    db.flush()
    return shared_list


def test_owned_rows_carry_no_claim_state(
    client, member_headers, owned_list_with_a_claim
):
    """The leak ADR 0003 was written about: `claimed_count` on `GET /lists`."""
    response = client.get("/lists?filter=owned", headers=member_headers)
    assert response.status_code == 200
    assert response.json(), "the fixture list should be in scope"
    _assert_blind(response.json())


def test_the_unfiltered_scope_is_blind_on_the_rows_the_caller_owns(
    client, member_headers, owned_list_with_a_claim
):
    """`GET /lists` with no filter mixes owned and shared rows, which is why the
    schema is chosen per row rather than declared once on the endpoint."""
    response = client.get("/lists", headers=member_headers)
    assert response.status_code == 200
    owned = [
        row for row in response.json() if row["id"] == owned_list_with_a_claim.id
    ]
    assert owned, "the fixture list should be in scope"
    _assert_blind(owned)


def test_list_detail_is_blind_for_its_owner(
    client, member_headers, owned_list_with_a_claim
):
    response = client.get(
        f"/lists/{owned_list_with_a_claim.id}", headers=member_headers
    )
    assert response.status_code == 200
    assert len(response.json()["gifts"]) == 2
    _assert_blind(response.json())


def test_creating_and_updating_a_list_answers_blind(client, member_headers):
    created = client.post("/lists", headers=member_headers, json={"name": "Fresh"})
    assert created.status_code == 201
    _assert_blind(created.json())

    updated = client.put(
        f"/lists/{created.json()['id']}",
        headers=member_headers,
        json={"name": "Renamed"},
    )
    assert updated.status_code == 200
    _assert_blind(updated.json())


def test_a_viewer_still_gets_the_claimed_count(
    client, admin_headers, admin_user, owned_list_with_a_claim
):
    """The other half of the rule: hiding it from the owner must not hide it
    from the people it is for."""
    response = client.get("/lists?filter=shared", headers=admin_headers)
    assert response.status_code == 200
    row = next(
        row for row in response.json() if row["id"] == owned_list_with_a_claim.id
    )
    assert row["claimed_count"] == 1
    assert row["gift_count"] == 2


def test_a_viewer_sees_the_claim_on_the_gift(
    client, admin_headers, admin_user, owned_list_with_a_claim
):
    response = client.get(
        f"/lists/{owned_list_with_a_claim.id}", headers=admin_headers
    )
    assert response.status_code == 200
    claimed = next(g for g in response.json()["gifts"] if g["name"] == "Claimed")
    assert claimed["claimed_by_id"] == admin_user.id
    assert claimed["purchased_at"] is not None
    assert claimed["amount_paid"] == "31.50"


def test_a_connections_lists_carry_the_count(
    client, admin_headers, connection, owned_list_with_a_claim
):
    response = client.get(
        f"/connections/{connection.id}/lists", headers=admin_headers
    )
    assert response.status_code == 200
    row = next(
        row for row in response.json() if row["id"] == owned_list_with_a_claim.id
    )
    assert row["claimed_count"] == 1
    # The admin's one claim here is already bought, so nothing is left to buy —
    # but the field is required on the viewer schema, so its presence is proof
    # the count was computed for this endpoint rather than defaulted.
    assert row["my_unpurchased_claim_count"] == 0


def test_a_folders_rows_keep_the_count_for_the_lists_it_does_not_own(
    client, db, admin_user, admin_headers, owned_list_with_a_claim
):
    """A folder groups lists its owner mostly did not write, so its rows are a
    mix — and the shared ones must keep their count rather than being narrowed
    to the owner schema on the way out."""
    from app.models.folder import Folder
    from app.models.folder_item import FolderItem

    folder = Folder(name="Admin's Shopping", owner_id=admin_user.id)
    db.add(folder)
    db.flush()
    db.add(FolderItem(folder_id=folder.id, list_id=owned_list_with_a_claim.id))
    db.flush()

    # A second gift on the same list, claimed by the admin and not yet bought:
    # this is what the folder row's badge has to surface.
    to_buy = Gift(list_id=owned_list_with_a_claim.id, name="Still to buy")
    db.add(to_buy)
    db.flush()
    db.add(
        Claim(
            gift_id=to_buy.id,
            user_id=admin_user.id,
            claimed_at=datetime.now(timezone.utc),
        )
    )
    db.flush()

    response = client.get(f"/folders/{folder.id}", headers=admin_headers)
    assert response.status_code == 200
    row = next(
        r for r in response.json()["lists"] if r["id"] == owned_list_with_a_claim.id
    )
    assert row["claimed_count"] == 2
    assert row["my_unpurchased_claim_count"] == 1


def test_a_folders_rows_stay_blind_on_the_owners_own_lists(
    client, db, member_user, member_headers, owned_list_with_a_claim
):
    from app.models.folder import Folder
    from app.models.folder_item import FolderItem

    folder = Folder(name="Member's Own", owner_id=member_user.id)
    db.add(folder)
    db.flush()
    db.add(FolderItem(folder_id=folder.id, list_id=owned_list_with_a_claim.id))
    db.flush()

    response = client.get(f"/folders/{folder.id}", headers=member_headers)
    assert response.status_code == 200
    assert response.json()["lists"], "the fixture list should be in the folder"
    _assert_blind(response.json()["lists"])


def test_a_viewer_gets_their_own_unpurchased_count(
    client, admin_headers, owned_list_with_a_claim
):
    """The same two halves for `my_unpurchased_claim_count` (NEU-1279): absent
    from every owner-facing payload above — `CLAIM_KEYS` carries it, so every
    sweep in this file already checks that — and present for the viewer it is
    about. Here the admin's one claim is already bought, so nothing is to buy."""
    response = client.get("/lists?filter=shared", headers=admin_headers)
    assert response.status_code == 200
    row = next(
        row for row in response.json() if row["id"] == owned_list_with_a_claim.id
    )
    assert row["claimed_count"] == 1
    assert row["my_unpurchased_claim_count"] == 0


def test_the_occasion_index_is_blind_on_an_occasion_holding_the_owners_list(
    client, db, member_user, member_headers, owned_list_with_a_claim
):
    """`GET /occasions` sorts on `last_activity_at`, which makes the *order* of
    this payload a place claim state can leak from even though no field in it
    is claim-shaped (ADR 0005, NEU-1292).

    The fixture's list is the caller's own and carries the admin's claim, so
    the sweep below and the two counts must all read as if nothing had been
    claimed at all.
    """
    from app.models.family import Family
    from app.models.family_member import FamilyMember
    from app.models.list_occasion_share import ListOccasionShare
    from app.models.occasion import Occasion

    family = Family(name="Boone Family", created_by_id=member_user.id)
    db.add(family)
    db.flush()
    db.add(
        FamilyMember(family_id=family.id, user_id=member_user.id, role="organizer")
    )
    occasion = Occasion(
        family_id=family.id, name="Christmas 2026", created_by_id=member_user.id
    )
    db.add(occasion)
    db.flush()
    db.add(
        ListOccasionShare(
            list_id=owned_list_with_a_claim.id, occasion_id=occasion.id
        )
    )
    db.flush()

    response = client.get("/occasions", headers=member_headers)
    assert response.status_code == 200
    row = next(r for r in response.json() if r["id"] == occasion.id)

    _assert_blind(response.json())
    assert row["list_count"] == 1
    assert row["my_claimed_count"] == 0
    assert row["my_bought_count"] == 0
