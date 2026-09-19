"""Giftee budgets — the split beneath the overall (NEU-1326).

One test per acceptance criterion, at the criterion's grain. The giftee set is
the union of three sources (visible lists in scope, the lists behind the
caller's claims, the caller's own budget rows), and the tests that matter most
are the ones proving nothing that counts toward `allocated` can be invisible,
and nothing on `giftees[]` reveals another account's claim, spend or budget.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.budgets.giftees import key_for
from app.dependencies import create_access_token
from app.models.account_person import AccountPerson
from app.models.claim import Claim
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.giftee_budget import GifteeBudget
from app.models.list_occasion_share import ListOccasionShare
from app.models.list_share import ListShare
from app.models.occasion import Occasion
from app.models.user import User

BOUGHT = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)


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


def _member(db, family, email, name) -> User:
    user = User(email=email, name=name, role="member", password_hash="x")
    user.set_password("x")
    db.add(user)
    db.flush()
    db.add(FamilyMember(family_id=family.id, user_id=user.id, role="member"))
    db.flush()
    return user


def _headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.fixture
def other(db, family):
    return _member(db, family, "other@test.com", "Other")


@pytest.fixture
def other_headers(other):
    return _headers(other)


@pytest.fixture
def jane(db, family):
    return _member(db, family, "jane@test.com", "Jane")


@pytest.fixture
def jane_headers(jane):
    return _headers(jane)


def _list(
    db, owner, name, occasion=None, recipient_name=None, account_person_id=None
) -> GiftList:
    gl = GiftList(
        name=name,
        owner_id=owner.id,
        recipient_name=recipient_name,
        account_person_id=account_person_id,
    )
    db.add(gl)
    db.flush()
    if occasion is not None:
        db.add(ListOccasionShare(list_id=gl.id, occasion_id=occasion.id))
        db.flush()
    db.refresh(gl)
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


def _giftee(block, key) -> dict:
    return next(g for g in block["giftees"] if g["key"] == key)


def _keys(block) -> list[str]:
    return [g["key"] for g in block["giftees"]]


def _shopping(client, headers, occasion) -> dict:
    return client.get(f"/occasions/{occasion.id}/shopping", headers=headers).json()


def _put(client, headers, occasion, key, amount):
    return client.put(
        f"/occasions/{occasion.id}/giftees/{key}/budget",
        json={"amount": amount},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# The payload, and the giftee set (criteria 1–4)
# ---------------------------------------------------------------------------


def test_shopping_carries_giftees_and_every_item_names_one(
    client, db, member_user, member_headers, occasion, other, folder
):
    """Both scopes return `{ budget, giftees, items }`, and every distinct key
    on `items` has an entry in `giftees` — the client never groups a row under
    a heading it does not have."""
    gl = _list(db, other, "Other's List", occasion=occasion)
    _claim(db, gl, member_user, "Puzzle", occasion=occasion)
    db.add(FolderItem(folder_id=folder.id, list_id=gl.id))
    db.flush()

    for url in (f"/occasions/{occasion.id}/shopping", f"/folders/{folder.id}/shopping"):
        payload = client.get(url, headers=member_headers).json()

        assert set(payload) == {"budget", "giftees", "items"}
        assert [item["giftee_key"] for item in payload["items"]] == [key_for(gl)]
        assert {item["giftee_key"] for item in payload["items"]} <= set(
            _keys(payload)
        )
        assert _giftee(payload, key_for(gl)) == {
            "key": f"owner:{other.id}",
            "kind": "owner",
            "name": "Other",
            "keeper": None,
            "list_count": 1,
            "budget": {
                "amount": None,
                "spent": "0.00",
                "remaining": None,
                "bought_count": 0,
                "total_count": 1,
                "unpriced_count": 0,
                "allocated": "0.00",
                "unallocated": None,
                "target": None,
                "allocation_count": 0,
            },
        }


def test_giftees_are_the_union_of_three_sources(
    client, db, member_user, member_headers, occasion, other, other_headers, jane
):
    """A visible list with nothing claimed, a claim on a list since unshared,
    and a budget row whose list has left the scope: each is a group."""
    visible = _list(db, other, "Nothing claimed yet", occasion=occasion)
    claimed = _list(db, jane, "Claimed then unshared", occasion=occasion)
    _claim(db, claimed, member_user, "Puzzle", occasion=occasion)
    budgeted = _list(db, other, "For Gran", occasion=occasion, recipient_name="Gran")
    assert _put(client, member_headers, occasion, key_for(budgeted), "40.00").status_code == 200

    # Unshare both: the claim keeps its group by source 2, the budget by source 3.
    for gl in (claimed, budgeted):
        db.execute(
            ListOccasionShare.__table__.delete().where(
                ListOccasionShare.list_id == gl.id
            )
        )
    db.flush()

    payload = _shopping(client, member_headers, occasion)

    assert set(_keys(payload)) == {key_for(visible), key_for(claimed), key_for(budgeted)}
    assert _giftee(payload, key_for(visible))["list_count"] == 1
    assert _giftee(payload, key_for(claimed))["budget"]["total_count"] == 1
    orphan = _giftee(payload, key_for(budgeted))
    assert orphan["name"] == "Gran"
    assert orphan["keeper"] == "Other"
    assert orphan["list_count"] == 0
    assert orphan["budget"]["amount"] == "40.00"
    assert payload["budget"]["allocated"] == "40.00"


def test_the_callers_own_list_and_an_unviewable_list_contribute_nothing(
    client, db, member_user, member_headers, occasion, other, folder, sample_list
):
    """A list the caller owns is dropped — they cannot claim on it. A folder
    item that outlived the share behind it is not a grant (invariant 2)."""
    db.add(ListOccasionShare(list_id=sample_list.id, occasion_id=occasion.id))
    unviewable = _list(db, other, "Share revoked")
    db.add(FolderItem(folder_id=folder.id, list_id=unviewable.id))
    db.add(FolderItem(folder_id=folder.id, list_id=sample_list.id))
    db.flush()

    assert _keys(_shopping(client, member_headers, occasion)) == []
    assert (
        _keys(client.get(f"/folders/{folder.id}/shopping", headers=member_headers).json())
        == []
    )


def test_lists_agreeing_on_the_triple_are_one_giftee(
    client, db, member_headers, occasion, other, jane
):
    """Two unmarked lists by one owner are one giftee; two lists one keeper
    keeps for "Beth" are one; "Beth" kept by two owners is two; a list marked
    for an account person is keyed on the person, not the owner."""
    _list(db, other, "Other's Christmas", occasion=occasion)
    _list(db, other, "Other's Stocking", occasion=occasion)
    beth_a = _list(db, other, "Beth 1", occasion=occasion, recipient_name="Beth")
    _list(db, other, "Beth 2", occasion=occasion, recipient_name="Beth")
    beth_by_jane = _list(db, jane, "Beth 3", occasion=occasion, recipient_name="Beth")
    jane.is_shared_account = True
    gran = AccountPerson(user_id=jane.id, name="Gran", position=0)
    db.add(gran)
    db.flush()
    for_gran = _list(db, jane, "Gran's list", occasion=occasion, account_person_id=gran.id)

    payload = _shopping(client, member_headers, occasion)

    by_key = {g["key"]: g for g in payload["giftees"]}
    assert set(by_key) == {
        f"owner:{other.id}",
        key_for(beth_a),
        key_for(beth_by_jane),
        f"person:{gran.id}",
    }
    assert by_key[f"owner:{other.id}"]["list_count"] == 2
    assert by_key[key_for(beth_a)] == {
        "key": key_for(beth_a),
        "kind": "absent",
        "name": "Beth",
        "keeper": "Other",
        "list_count": 2,
        "budget": by_key[key_for(beth_a)]["budget"],
    }
    assert by_key[key_for(beth_by_jane)]["keeper"] == "Jane"
    assert key_for(beth_a) != key_for(beth_by_jane)
    assert by_key[f"person:{gran.id}"]["kind"] == "person"
    assert by_key[f"person:{gran.id}"]["name"] == "Gran"
    assert by_key[f"person:{gran.id}"]["keeper"] == "Jane"
    assert key_for(for_gran) == f"person:{gran.id}"


def test_giftees_with_items_come_first_then_by_name_then_key(
    client, db, member_user, member_headers, occasion, family
):
    zed = _member(db, family, "zed@test.com", "Zed")
    amy = _member(db, family, "amy@test.com", "amy")
    bob = _member(db, family, "bob@test.com", "Bob")
    carl = _member(db, family, "carl@test.com", "Carl")
    for owner in (carl, bob, zed, amy):
        gl = _list(db, owner, f"{owner.name}'s list", occasion=occasion)
        if owner in (zed, amy):
            _claim(db, gl, member_user, "Something", occasion=occasion)

    payload = _shopping(client, member_headers, occasion)

    assert [g["name"] for g in payload["giftees"]] == ["amy", "Zed", "Bob", "Carl"]


# ---------------------------------------------------------------------------
# PUT / DELETE .../giftees/{key}/budget (criteria 5–8)
# ---------------------------------------------------------------------------


def test_put_creates_the_row_and_answers_with_the_block(
    client, db, member_headers, occasion, other, jane, jane_headers
):
    gl = _list(db, other, "Other's List", occasion=occasion)

    response = _put(client, member_headers, occasion, key_for(gl), "150.00")

    assert response.status_code == 200
    block = response.json()
    assert set(block) == {"budget", "giftees"}
    assert block["budget"]["allocated"] == "150.00"
    assert block["budget"]["allocation_count"] == 1
    assert block["budget"]["amount"] is None
    assert block["budget"]["target"] == "150.00"
    assert block["budget"]["remaining"] == "150.00"
    assert _giftee(block, key_for(gl))["budget"] == {
        "amount": "150.00",
        "spent": "0.00",
        "remaining": "150.00",
        "bought_count": 0,
        "total_count": 0,
        "unpriced_count": 0,
        "allocated": "0.00",
        "unallocated": None,
        "target": "150.00",
        "allocation_count": 0,
    }
    # A second member of the family, reading the same giftee, sees nothing.
    theirs = _shopping(client, jane_headers, occasion)
    assert _giftee(theirs, key_for(gl))["budget"]["amount"] is None
    assert theirs["budget"]["allocated"] == "0.00"
    assert theirs["budget"]["allocation_count"] == 0


def test_put_replaces_the_existing_amount(client, db, member_headers, occasion, other):
    gl = _list(db, other, "Other's List", occasion=occasion)
    _put(client, member_headers, occasion, key_for(gl), "150.00")

    block = _put(client, member_headers, occasion, key_for(gl), "175.00").json()

    assert _giftee(block, key_for(gl))["budget"]["amount"] == "175.00"
    assert block["budget"]["allocated"] == "175.00"
    assert block["budget"]["allocation_count"] == 1


def test_delete_answers_with_the_block(client, db, member_headers, occasion, other):
    gl = _list(db, other, "Other's List", occasion=occasion)
    _put(client, member_headers, occasion, key_for(gl), "150.00")

    response = client.delete(
        f"/occasions/{occasion.id}/giftees/{key_for(gl)}/budget", headers=member_headers
    )

    assert response.status_code == 200
    block = response.json()
    assert _giftee(block, key_for(gl))["budget"]["amount"] is None
    assert block["budget"]["allocated"] == "0.00"
    assert block["budget"]["allocation_count"] == 0
    assert block["budget"]["target"] is None


def test_delete_is_404_when_no_row_exists(client, db, member_headers, occasion, other):
    gl = _list(db, other, "Other's List", occasion=occasion)

    assert (
        client.delete(
            f"/occasions/{occasion.id}/giftees/{key_for(gl)}/budget",
            headers=member_headers,
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "key", ["bogus", "owner:abc", "person:", "absent:1", "absent:1:", "absent:1:!!!"]
)
def test_a_malformed_key_is_400(client, member_headers, occasion, key):
    assert _put(client, member_headers, occasion, key, "10.00").status_code == 400
    assert (
        client.delete(
            f"/occasions/{occasion.id}/giftees/{key}/budget", headers=member_headers
        ).status_code
        == 400
    )


def test_a_well_formed_key_for_a_giftee_not_in_scope_is_404(
    client, db, member_headers, occasion, other
):
    """The client can only have got a key from this scope's payload, so a miss
    means the list has since gone."""
    elsewhere = _list(db, other, "Not shared here")

    assert (
        _put(client, member_headers, occasion, key_for(elsewhere), "10.00").status_code
        == 404
    )
    assert _put(client, member_headers, occasion, "owner:999999", "10.00").status_code == 404


def test_giftee_endpoints_gate_like_the_overalls(
    client, db, admin_headers, member_headers, occasion, other, folder
):
    gl = _list(db, other, "Other's List", occasion=occasion)
    key = key_for(gl)

    # A non-member learns nothing — not even that the key is unknown to them.
    assert _put(client, admin_headers, occasion, key, "10.00").status_code == 403
    assert (
        client.delete(
            f"/occasions/{occasion.id}/giftees/{key}/budget", headers=admin_headers
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/occasions/999999/giftees/{key}/budget",
            json={"amount": "10.00"},
            headers=member_headers,
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/folders/{folder.id}/giftees/{key}/budget",
            json={"amount": "10.00"},
            headers=admin_headers,
        ).status_code
        == 403
    )
    assert (
        client.put(f"/occasions/{occasion.id}/giftees/{key}/budget", json={"amount": "10.00"})
        .status_code
        == 401
    )


def test_a_negative_giftee_budget_is_refused(client, db, member_headers, occasion, other):
    gl = _list(db, other, "Other's List", occasion=occasion)

    assert _put(client, member_headers, occasion, key_for(gl), "-1.00").status_code == 422


def test_folder_scope_hits_the_folder_path(
    client, db, member_user, member_headers, folder, other
):
    gl = _list(db, other, "Other's List")
    db.add(ListShare(list_id=gl.id, user_id=member_user.id))
    db.add(FolderItem(folder_id=folder.id, list_id=gl.id))
    db.flush()

    put = client.put(
        f"/folders/{folder.id}/giftees/{key_for(gl)}/budget",
        json={"amount": "60.00"},
        headers=member_headers,
    )
    assert put.status_code == 200
    assert put.json()["budget"]["allocated"] == "60.00"
    assert _giftee(put.json(), key_for(gl))["budget"]["amount"] == "60.00"

    cleared = client.delete(
        f"/folders/{folder.id}/giftees/{key_for(gl)}/budget", headers=member_headers
    )
    assert cleared.status_code == 200
    assert cleared.json()["budget"]["allocated"] == "0.00"
    assert (
        client.delete(
            f"/folders/{folder.id}/giftees/{key_for(gl)}/budget", headers=member_headers
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Per-giftee spend and the overall (criteria 9, 11)
# ---------------------------------------------------------------------------


def test_per_giftee_spend_counts_that_giftees_lists_alone_and_sums_to_the_overall(
    client, db, member_user, member_headers, occasion, other, jane
):
    """Spend follows the tick and unpriced is disclosed per giftee — inherited,
    because the aggregates are shared, not copied."""
    others = _list(db, other, "Other's List", occasion=occasion)
    janes = _list(db, jane, "Jane's List", occasion=occasion)
    _claim(db, others, member_user, "Shoes", occasion=occasion, purchased_at=BOUGHT, amount_paid=Decimal("85.00"))
    _claim(db, others, member_user, "Socks", occasion=occasion, purchased_at=BOUGHT)
    _claim(db, others, member_user, "Skillet", occasion=occasion, amount_paid=Decimal("20.00"))
    _claim(db, janes, member_user, "Puzzle", occasion=occasion, purchased_at=BOUGHT, amount_paid=Decimal("18.00"))

    payload = _shopping(client, member_headers, occasion)

    other_budget = _giftee(payload, key_for(others))["budget"]
    jane_budget = _giftee(payload, key_for(janes))["budget"]
    assert (other_budget["spent"], other_budget["bought_count"], other_budget["total_count"], other_budget["unpriced_count"]) == ("85.00", 2, 3, 1)
    assert (jane_budget["spent"], jane_budget["bought_count"], jane_budget["total_count"], jane_budget["unpriced_count"]) == ("18.00", 1, 1, 0)
    overall = payload["budget"]
    assert (overall["spent"], overall["bought_count"], overall["total_count"], overall["unpriced_count"]) == ("103.00", 3, 4, 1)


def test_the_overall_and_the_giftee_rows_never_write_each_other(
    client, db, member_user, member_headers, occasion, other
):
    gl = _list(db, other, "Other's List", occasion=occasion)
    _put(client, member_headers, occasion, key_for(gl), "150.00")

    client.put(f"/occasions/{occasion.id}/budget", json={"amount": "200.00"}, headers=member_headers)
    client.delete(f"/occasions/{occasion.id}/budget", headers=member_headers)
    rows = db.query(GifteeBudget).filter(GifteeBudget.user_id == member_user.id).all()
    assert [(r.giftee_key, r.amount) for r in rows] == [(key_for(gl), Decimal("150.00"))]

    client.put(f"/occasions/{occasion.id}/budget", json={"amount": "200.00"}, headers=member_headers)
    _put(client, member_headers, occasion, key_for(gl), "175.00")
    client.delete(f"/occasions/{occasion.id}/giftees/{key_for(gl)}/budget", headers=member_headers)
    assert _shopping(client, member_headers, occasion)["budget"]["amount"] == "200.00"


# ---------------------------------------------------------------------------
# Orphans: a giftee whose lists have gone, or been renamed (criteria 12, 13)
# ---------------------------------------------------------------------------


def test_an_orphaned_giftee_budget_still_shows_and_counts(
    client, db, member_user, member_headers, occasion, other, other_headers, folder
):
    """Share revoked on the occasion, list removed from the folder: the row
    stays, shows as an empty group, and counts toward `allocated`."""
    gl = _list(db, other, "Other's List", occasion=occasion)
    db.add(ListShare(list_id=gl.id, user_id=member_user.id))
    db.add(FolderItem(folder_id=folder.id, list_id=gl.id))
    db.flush()
    _put(client, member_headers, occasion, key_for(gl), "150.00")
    client.put(f"/folders/{folder.id}/giftees/{key_for(gl)}/budget", json={"amount": "60.00"}, headers=member_headers)

    assert client.delete(f"/lists/{gl.id}/occasions/{occasion.id}", headers=other_headers).status_code == 204
    assert client.delete(f"/folders/{folder.id}/items/{gl.id}", headers=member_headers).status_code == 204

    occasion_payload = _shopping(client, member_headers, occasion)
    folder_payload = client.get(f"/folders/{folder.id}/shopping", headers=member_headers).json()
    for payload, amount in ((occasion_payload, "150.00"), (folder_payload, "60.00")):
        orphan = _giftee(payload, key_for(gl))
        assert orphan["name"] == "Other"
        assert orphan["list_count"] == 0
        assert orphan["budget"]["amount"] == amount
        assert orphan["budget"]["total_count"] == 0
        assert payload["budget"]["allocated"] == amount
        assert payload["budget"]["target"] == amount


def test_renaming_a_recipient_leaves_the_old_giftee_budget_behind(
    client, db, member_headers, occasion, other
):
    """A recipient rename is not followed (ADR 0006): the old name is an empty
    group carrying its budget, the new name starts with none."""
    gl = _list(db, other, "For Beth", occasion=occasion, recipient_name="Beth")
    old_key = key_for(gl)
    _put(client, member_headers, occasion, old_key, "75.00")

    gl.recipient_name = "Bethany"
    db.flush()
    new_key = key_for(gl)

    payload = _shopping(client, member_headers, occasion)
    old = _giftee(payload, old_key)
    new = _giftee(payload, new_key)
    assert (old["name"], old["keeper"], old["list_count"], old["budget"]["amount"]) == ("Beth", "Other", 0, "75.00")
    assert (new["name"], new["list_count"], new["budget"]["amount"]) == ("Bethany", 1, None)
    assert payload["budget"]["allocated"] == "75.00"


# ---------------------------------------------------------------------------
# Cascades (criterion 14)
# ---------------------------------------------------------------------------


def test_deleting_an_account_person_takes_every_giftee_budget_keyed_on_it(
    client, db, member_headers, occasion, other, other_headers, jane, jane_headers, folder
):
    """Through `PUT /account`, in every scope, for every user — before the
    people rows go, or the FK refuses."""
    other.is_shared_account = True
    gran = AccountPerson(user_id=other.id, name="Gran", position=0)
    grandpa = AccountPerson(user_id=other.id, name="Grandpa", position=1)
    db.add_all([gran, grandpa])
    db.flush()
    gl = _list(db, other, "Gran's list", occasion=occasion, account_person_id=gran.id)
    db.add(FolderItem(folder_id=folder.id, list_id=gl.id))
    db.flush()
    assert _put(client, member_headers, occasion, f"person:{gran.id}", "100.00").status_code == 200
    assert _put(client, jane_headers, occasion, f"person:{gran.id}", "90.00").status_code == 200
    assert client.put(f"/folders/{folder.id}/giftees/person:{gran.id}/budget", json={"amount": "80.00"}, headers=member_headers).status_code == 200

    response = client.put(
        "/account?confirm=true",
        json={"is_shared_account": True, "people": [{"id": grandpa.id, "name": "Grandpa"}]},
        headers=other_headers,
    )

    assert response.status_code == 200
    assert db.query(GifteeBudget).filter(GifteeBudget.account_person_id == gran.id).count() == 0
    payload = _shopping(client, member_headers, occasion)
    assert payload["budget"]["allocated"] == "0.00"
    assert _keys(payload) == [f"owner:{other.id}"]


def test_deleting_a_folder_takes_its_giftee_budgets(
    client, db, member_user, member_headers, folder, other
):
    gl = _list(db, other, "Other's List")
    db.add(ListShare(list_id=gl.id, user_id=member_user.id))
    db.add(FolderItem(folder_id=folder.id, list_id=gl.id))
    db.flush()
    client.put(f"/folders/{folder.id}/giftees/{key_for(gl)}/budget", json={"amount": "60.00"}, headers=member_headers)

    assert client.delete(f"/folders/{folder.id}", headers=member_headers).status_code == 204
    assert db.query(GifteeBudget).filter(GifteeBudget.folder_id == folder.id).count() == 0


def test_deleting_a_family_takes_the_giftee_budgets_on_its_occasions(
    client, db, member_headers, family, occasion, other, jane, jane_headers
):
    gl = _list(db, other, "Other's List", occasion=occasion)
    _put(client, member_headers, occasion, key_for(gl), "150.00")
    _put(client, jane_headers, occasion, key_for(gl), "90.00")

    assert client.delete(f"/families/{family.id}", headers=member_headers).status_code == 204
    assert db.query(GifteeBudget).filter(GifteeBudget.occasion_id == occasion.id).count() == 0


@pytest.fixture
def stranger(db):
    """A list owner in no family, so a purge has nothing family-shaped to trip
    on — the existing purge tests make the same choice."""
    user = User(email="stranger@test.com", name="Stranger", role="member", password_hash="x")
    user.set_password("x")
    db.add(user)
    db.flush()
    return user


def test_purging_a_user_takes_the_giftee_budgets_they_set(
    client, db, admin_headers, member_user, member_headers, folder, stranger
):
    gl = _list(db, stranger, "Stranger's List")
    db.add(ListShare(list_id=gl.id, user_id=member_user.id))
    db.add(FolderItem(folder_id=folder.id, list_id=gl.id))
    db.flush()
    assert client.put(f"/folders/{folder.id}/giftees/{key_for(gl)}/budget", json={"amount": "60.00"}, headers=member_headers).status_code == 200

    assert client.delete(f"/users/{member_user.id}?purge=true", headers=admin_headers).status_code == 204
    assert db.query(GifteeBudget).filter(GifteeBudget.user_id == member_user.id).count() == 0


def test_purging_a_user_takes_the_giftee_budgets_resolving_through_their_lists(
    client, db, admin_headers, member_user, member_headers, folder, stranger
):
    """The other direction: somebody else's row keyed on the purged user's
    list goes too — their lists are going, and with them every giftee those
    lists named."""
    gl = _list(db, stranger, "Stranger's List")
    db.add(ListShare(list_id=gl.id, user_id=member_user.id))
    db.add(FolderItem(folder_id=folder.id, list_id=gl.id))
    db.flush()
    assert client.put(f"/folders/{folder.id}/giftees/{key_for(gl)}/budget", json={"amount": "60.00"}, headers=member_headers).status_code == 200

    assert client.delete(f"/users/{stranger.id}?purge=true", headers=admin_headers).status_code == 204

    assert db.query(GifteeBudget).filter(GifteeBudget.owner_id == stranger.id).count() == 0
    payload = client.get(f"/folders/{folder.id}/shopping", headers=member_headers).json()
    assert payload["giftees"] == []
    assert payload["budget"]["allocated"] == "0.00"


def test_giftee_endpoints_404_an_unknown_folder(client, member_headers):
    assert (
        client.put(
            "/folders/999999/giftees/owner:1/budget",
            json={"amount": "10.00"},
            headers=member_headers,
        ).status_code
        == 404
    )
    assert (
        client.delete("/folders/999999/giftees/owner:1/budget", headers=member_headers).status_code
        == 404
    )


def test_an_orphaned_giftee_budget_can_still_be_edited(
    client, db, member_headers, occasion, other, other_headers
):
    """A deliberate widening of decision 5's "in sources 1 or 2, else 404": an
    orphaned row is rendered as a group carrying an editor, and a 404 behind
    that editor would be a broken button. The row already exists, so editing
    it reveals nothing the caller could not already see."""
    gl = _list(db, other, "Other's List", occasion=occasion)
    _put(client, member_headers, occasion, key_for(gl), "150.00")
    assert client.delete(f"/lists/{gl.id}/occasions/{occasion.id}", headers=other_headers).status_code == 204

    response = _put(client, member_headers, occasion, key_for(gl), "175.00")

    assert response.status_code == 200
    orphan = _giftee(response.json(), key_for(gl))
    assert orphan["list_count"] == 0
    assert orphan["budget"]["amount"] == "175.00"
    assert response.json()["budget"]["allocated"] == "175.00"
