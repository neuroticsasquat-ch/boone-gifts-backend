"""GET/PUT /account — the shared-account flag and its people.

Account people are labels, not identities: nothing here touches visibility,
claims or membership. See docs/adr/0001-shared-accounts-are-one-identity.md.
"""
import pytest

from app.models.account_person import AccountPerson
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_share import ListShare


def _put(client, headers, people, shared=True, confirm=None):
    url = "/account" if confirm is None else f"/account?confirm={str(confirm).lower()}"
    return client.put(
        url,
        headers=headers,
        json={"is_shared_account": shared, "people": people},
    )


@pytest.fixture
def shared_account(client, member_headers):
    """A member account marked shared, with Gran and Grandpa on it."""
    response = _put(client, member_headers, [{"name": "Gran"}, {"name": "Grandpa"}])
    assert response.status_code == 200
    return response.json()


def _person_names(db, owner):
    """The people actually on the account, read straight from the table.

    SQLite reuses a freed rowid, so a person id from before a delete can name a
    *different* person afterwards — assert on names, not on ids being gone."""
    rows = db.query(AccountPerson).filter(AccountPerson.user_id == owner.id)
    return [person.name for person in rows.order_by(AccountPerson.position)]


def _labelled_list(db, owner, person, name="Gran's List"):
    gift_list = GiftList(name=name, owner_id=owner.id, account_person_id=person["id"])
    db.add(gift_list)
    db.flush()
    return gift_list


# --- GET ---


def test_get_account_defaults_to_not_shared(client, member_headers):
    response = client.get("/account", headers=member_headers)
    assert response.status_code == 200
    assert response.json() == {"is_shared_account": False, "people": []}


def test_get_account_requires_auth(client):
    assert client.get("/account").status_code == 401


def test_get_account_returns_people_in_order(client, member_headers, shared_account):
    body = client.get("/account", headers=member_headers).json()
    assert body["is_shared_account"] is True
    assert [p["name"] for p in body["people"]] == ["Gran", "Grandpa"]


def test_account_people_are_scoped_to_the_caller(
    client, member_headers, admin_headers, shared_account
):
    assert client.get("/account", headers=admin_headers).json() == {
        "is_shared_account": False,
        "people": [],
    }


# --- PUT: create, rename, reorder, add ---


def test_put_creates_people_and_marks_shared(client, member_headers):
    body = _put(client, member_headers, [{"name": "Gran"}, {"name": "Grandpa"}]).json()
    assert body["is_shared_account"] is True
    assert [p["name"] for p in body["people"]] == ["Gran", "Grandpa"]
    assert all(isinstance(p["id"], int) for p in body["people"])


def test_put_strips_whitespace_from_names(client, member_headers):
    body = _put(client, member_headers, [{"name": "  Gran  "}, {"name": "Grandpa"}]).json()
    assert [p["name"] for p in body["people"]] == ["Gran", "Grandpa"]


def test_put_renames_in_place(client, member_headers, shared_account):
    gran, grandpa = shared_account["people"]
    body = _put(
        client, member_headers,
        [{"id": gran["id"], "name": "Nan"}, {"id": grandpa["id"], "name": "Grandpa"}],
    ).json()
    assert [(p["id"], p["name"]) for p in body["people"]] == [
        (gran["id"], "Nan"), (grandpa["id"], "Grandpa")
    ]


def test_put_accepts_a_no_op_rename(client, member_headers, shared_account):
    gran, grandpa = shared_account["people"]
    body = _put(
        client, member_headers,
        [{"id": gran["id"], "name": "Gran"}, {"id": grandpa["id"], "name": "Grandpa"}],
    ).json()
    assert body["people"] == shared_account["people"]


def test_put_swaps_two_names(client, member_headers, shared_account):
    # The awkward case: both names change and each lands on the other's, which
    # would trip the (user_id, name) unique constraint applied naively.
    gran, grandpa = shared_account["people"]
    response = _put(
        client, member_headers,
        [{"id": gran["id"], "name": "Grandpa"}, {"id": grandpa["id"], "name": "Gran"}],
    )
    assert response.status_code == 200
    assert [(p["id"], p["name"]) for p in response.json()["people"]] == [
        (gran["id"], "Grandpa"), (grandpa["id"], "Gran")
    ]


def test_put_reorders_by_array_order(client, member_headers, shared_account):
    gran, grandpa = shared_account["people"]
    body = _put(
        client, member_headers,
        [{"id": grandpa["id"], "name": "Grandpa"}, {"id": gran["id"], "name": "Gran"}],
    ).json()
    assert [p["name"] for p in body["people"]] == ["Grandpa", "Gran"]
    # And the new order sticks, rather than being an artefact of the response.
    assert [p["name"] for p in client.get("/account", headers=member_headers).json()["people"]] == [
        "Grandpa", "Gran"
    ]


def test_put_adds_a_third_person(client, member_headers, shared_account):
    people = [{"id": p["id"], "name": p["name"]} for p in shared_account["people"]]
    body = _put(client, member_headers, people + [{"name": "Dot"}]).json()
    assert [p["name"] for p in body["people"]] == ["Gran", "Grandpa", "Dot"]


def test_put_reuses_a_freed_name_in_one_request(
    client, db, member_user, member_headers, shared_account
):
    # Deleting "Grandpa" and creating a new "Grandpa" in the same replace: the
    # delete has to reach the database before the insert does, or the
    # (user_id, name) unique constraint trips.
    gran = shared_account["people"][0]
    response = _put(
        client, member_headers,
        [{"id": gran["id"], "name": "Gran"}, {"name": "Grandpa"}],
    )
    assert response.status_code == 200
    assert [p["name"] for p in response.json()["people"]] == ["Gran", "Grandpa"]
    assert _person_names(db, member_user) == ["Gran", "Grandpa"]


# --- PUT: the shape rules (§4.3) ---


def test_marking_shared_with_one_person_is_400(client, member_headers):
    response = _put(client, member_headers, [{"name": "Gran"}])
    assert response.status_code == 400
    assert "two people" in response.json()["detail"]


def test_marking_shared_with_no_people_is_400(client, member_headers):
    assert _put(client, member_headers, []).status_code == 400


def test_duplicate_name_is_400(client, member_headers):
    response = _put(client, member_headers, [{"name": "Gran"}, {"name": "Gran"}])
    assert response.status_code == 400


def test_whitespace_only_name_is_400(client, member_headers):
    response = _put(client, member_headers, [{"name": "   "}, {"name": "Grandpa"}])
    assert response.status_code == 400


def test_another_accounts_person_id_is_404(
    client, member_headers, admin_headers, shared_account
):
    # Admin claims one of the member account's person ids. Not a 403: that would
    # confirm the id exists.
    stolen = shared_account["people"][0]["id"]
    response = _put(
        client, admin_headers, [{"id": stolen, "name": "Mine"}, {"name": "Other"}]
    )
    assert response.status_code == 404


def test_unknown_person_id_is_404(client, member_headers, shared_account):
    response = _put(
        client, member_headers, [{"id": 99999, "name": "Ghost"}, {"name": "Grandpa"}]
    )
    assert response.status_code == 404


# --- PUT: deleting down to one auto-unmarks (§4.3) ---


def test_deleting_down_to_one_person_unmarks_the_account(
    client, member_headers, shared_account
):
    gran = shared_account["people"][0]
    body = _put(client, member_headers, [{"id": gran["id"], "name": "Gran"}]).json()
    # The last person goes too: one person on an account labels nothing.
    assert body == {"is_shared_account": False, "people": []}


def test_deleting_every_person_unmarks_the_account(client, member_headers, shared_account):
    body = _put(client, member_headers, [], shared=False).json()
    assert body == {"is_shared_account": False, "people": []}


# --- PUT: the destructive-change 409 (§3.3) ---


def test_deleting_a_labelled_person_is_409(
    client, db, member_user, member_headers, shared_account
):
    gran, grandpa = shared_account["people"]
    _labelled_list(db, member_user, grandpa, name="Grandpa's List")
    _labelled_list(db, member_user, grandpa, name="Grandpa's Birthday")

    response = _put(
        client, member_headers,
        [{"id": gran["id"], "name": "Gran"}, {"name": "Dot"}],
    )

    assert response.status_code == 409
    assert response.json() == {"affected_lists": 2}


def test_unconfirmed_409_changes_nothing(
    client, db, member_user, member_headers, shared_account
):
    gran, grandpa = shared_account["people"]
    gift_list = _labelled_list(db, member_user, grandpa)

    _put(client, member_headers, [{"id": gran["id"], "name": "Gran"}, {"name": "Dot"}])

    db.expire_all()
    assert db.get(GiftList, gift_list.id).account_person_id == grandpa["id"]
    assert db.get(AccountPerson, grandpa["id"]) is not None
    assert db.get(AccountPerson, gran["id"]).name == "Gran"
    assert member_user.is_shared_account is True


def test_confirmed_409_commits(client, db, member_user, member_headers, shared_account):
    gran, grandpa = shared_account["people"]
    gift_list = _labelled_list(db, member_user, grandpa)

    response = _put(
        client, member_headers,
        [{"id": gran["id"], "name": "Gran"}, {"name": "Dot"}],
        confirm=True,
    )

    assert response.status_code == 200
    assert [p["name"] for p in response.json()["people"]] == ["Gran", "Dot"]
    db.expire_all()
    # §4.4: the label is nulled, the list itself survives.
    assert db.get(GiftList, gift_list.id).account_person_id is None
    assert _person_names(db, member_user) == ["Gran", "Dot"]


def test_unmarking_shared_with_labelled_lists_is_409(
    client, db, member_user, member_headers, shared_account
):
    gran, grandpa = shared_account["people"]
    _labelled_list(db, member_user, gran)
    _labelled_list(db, member_user, grandpa, name="Grandpa's List")

    people = [{"id": p["id"], "name": p["name"]} for p in shared_account["people"]]
    response = _put(client, member_headers, people, shared=False)

    assert response.status_code == 409
    # Unmarking strips every label, not just one person's.
    assert response.json() == {"affected_lists": 2}


def test_unmarking_shared_confirmed_clears_every_label(
    client, db, member_user, member_headers, shared_account
):
    gran, grandpa = shared_account["people"]
    first = _labelled_list(db, member_user, gran)
    second = _labelled_list(db, member_user, grandpa, name="Grandpa's List")

    people = [{"id": p["id"], "name": p["name"]} for p in shared_account["people"]]
    body = _put(client, member_headers, people, shared=False, confirm=True).json()

    assert body["is_shared_account"] is False
    # The people themselves were not asked to go, so they stay.
    assert [p["name"] for p in body["people"]] == ["Gran", "Grandpa"]
    db.expire_all()
    assert db.get(GiftList, first.id).account_person_id is None
    assert db.get(GiftList, second.id).account_person_id is None


def test_deleting_an_unlabelled_person_needs_no_confirmation(
    client, member_headers, shared_account
):
    people = [{"id": p["id"], "name": p["name"]} for p in shared_account["people"]]
    _put(client, member_headers, people + [{"name": "Dot"}])

    response = _put(client, member_headers, people)

    assert response.status_code == 200
    assert [p["name"] for p in response.json()["people"]] == ["Gran", "Grandpa"]


def test_deleting_down_to_one_labelled_person_is_409_then_commits(
    client, db, member_user, member_headers, shared_account
):
    gran, grandpa = shared_account["people"]
    gift_list = _labelled_list(db, member_user, gran)

    unconfirmed = _put(client, member_headers, [{"id": gran["id"], "name": "Gran"}])
    assert unconfirmed.status_code == 409
    assert unconfirmed.json() == {"affected_lists": 1}

    confirmed = _put(
        client, member_headers, [{"id": gran["id"], "name": "Gran"}], confirm=True
    )
    assert confirmed.json() == {"is_shared_account": False, "people": []}
    db.expire_all()
    assert db.get(GiftList, gift_list.id).account_person_id is None
    assert _person_names(db, member_user) == []


# --- §4.4: deleting a person nulls, never cascades ---


def test_deleting_a_person_leaves_the_list_and_its_gifts_intact(
    client, db, member_user, admin_user, member_headers, shared_account, connection
):
    gran, grandpa = shared_account["people"]
    gift_list = _labelled_list(db, member_user, grandpa)
    gift = Gift(list_id=gift_list.id, name="Fishing reel", claimed_by_id=admin_user.id)
    share = ListShare(list_id=gift_list.id, user_id=admin_user.id)
    db.add_all([gift, share])
    db.flush()

    _put(
        client, member_headers,
        [{"id": gran["id"], "name": "Gran"}, {"name": "Dot"}],
        confirm=True,
    )

    db.expire_all()
    assert db.get(GiftList, gift_list.id) is not None
    surviving = db.get(Gift, gift.id)
    assert surviving is not None
    # No claim is ever released by this ticket.
    assert surviving.claimed_by_id == admin_user.id
    assert db.get(ListShare, share.id) is not None


def test_staying_shared_with_no_people_is_400(client, member_headers, shared_account):
    # Not the auto-unmark case: "still shared, but nobody is on it" contradicts
    # itself, so it is refused rather than quietly answered with 200.
    response = _put(client, member_headers, [])
    assert response.status_code == 400
    assert "two people" in response.json()["detail"]


def test_staying_shared_with_one_person_still_auto_unmarks(
    client, member_headers, shared_account
):
    # The neighbouring case, pinned so the stricter empty-array rule above
    # cannot creep into it: dropping to one is a delete, not a contradiction.
    gran = shared_account["people"][0]
    response = _put(client, member_headers, [{"id": gran["id"], "name": "Gran"}])
    assert response.status_code == 200
    assert response.json() == {"is_shared_account": False, "people": []}
