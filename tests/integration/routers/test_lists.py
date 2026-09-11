from types import SimpleNamespace

import pytest

from app.dependencies import create_access_token
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.gift_list import GiftList
from app.models.list_occasion_share import ListOccasionShare
from app.models.list_share import ListShare
from app.models.occasion import Occasion
from app.models.user import User


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.fixture
def family_world(db):
    """Caller U; family F1 = {U, P}; family F2 = {U, P, Q}.
    P owns L_p (active) + L_p_archived; Q owns L_q; U owns L_u.
    L_p is ALSO manually shared with U."""

    def mkuser(email, name):
        u = User(email=email, name=name, role="member", password_hash="x")
        u.set_password("pw123456")
        db.add(u)
        db.flush()
        return u

    u = mkuser("u@test.com", "Caller U")
    p = mkuser("p@test.com", "Owner P")
    q = mkuser("q@test.com", "Owner Q")

    f1 = Family(name="F1 Family", created_by_id=u.id)
    f2 = Family(name="F2 Family", created_by_id=u.id)
    db.add_all([f1, f2])
    db.flush()
    db.add_all(
        [
            FamilyMember(family_id=f1.id, user_id=u.id, role="organizer"),
            FamilyMember(family_id=f1.id, user_id=p.id, role="member"),
            FamilyMember(family_id=f2.id, user_id=u.id, role="organizer"),
            FamilyMember(family_id=f2.id, user_id=p.id, role="member"),
            FamilyMember(family_id=f2.id, user_id=q.id, role="member"),
        ]
    )

    l_u = GiftList(name="U's List", owner_id=u.id)
    l_p = GiftList(name="P's List", owner_id=p.id)
    l_p_arch = GiftList(name="P's Archived", owner_id=p.id, is_archived=True)
    l_q = GiftList(name="Q's List", owner_id=q.id)
    db.add_all([l_u, l_p, l_p_arch, l_q])
    db.flush()

    o1 = Occasion(family_id=f1.id, name="F1 Christmas", created_by_id=u.id)
    o2 = Occasion(family_id=f2.id, name="F2 Christmas", created_by_id=u.id)
    db.add_all([o1, o2])
    db.flush()

    db.add(ListShare(list_id=l_p.id, user_id=u.id))  # L_p also manually shared with U
    # Family visibility is an explicit per-(list, occasion) share. These mirror
    # what the owners would have opted into: P shares to both families'
    # occasions, Q to F2's.
    db.add_all(
        [
            ListOccasionShare(list_id=l_p.id, occasion_id=o1.id),
            ListOccasionShare(list_id=l_p.id, occasion_id=o2.id),
            ListOccasionShare(list_id=l_p_arch.id, occasion_id=o1.id),
            ListOccasionShare(list_id=l_q.id, occasion_id=o2.id),
        ]
    )
    db.flush()

    return SimpleNamespace(
        u=u, p=p, q=q, f1=f1, f2=f2, o1=o1, o2=o2,
        l_u=l_u, l_p=l_p, l_p_arch=l_p_arch, l_q=l_q,
    )


def test_create_list(client, member_user, member_headers):
    response = client.post(
        "/lists",
        headers=member_headers,
        json={"name": "Birthday", "description": "My birthday list"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Birthday"
    assert data["description"] == "My birthday list"
    assert data["owner_id"] == member_user.id


def test_create_list_no_description(client, member_user, member_headers):
    response = client.post(
        "/lists",
        headers=member_headers,
        json={"name": "Minimal"},
    )
    assert response.status_code == 201
    assert response.json()["description"] is None


def test_create_list_unauthenticated(client):
    response = client.post("/lists", json={"name": "Nope"})
    assert response.status_code == 401


def test_list_lists_owned(client, member_user, member_headers, sample_list):
    response = client.get("/lists", headers=member_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "Member's Wishlist" in names


def test_list_lists_shared(client, admin_user, admin_headers, shared_list):
    response = client.get("/lists", headers=admin_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "Member's Wishlist" in names


def test_list_lists_excludes_unshared(client, admin_user, admin_headers, sample_list):
    response = client.get("/lists", headers=admin_headers)
    assert response.status_code == 200
    names = [l["name"] for l in response.json()]
    assert "Member's Wishlist" not in names


def test_list_lists_filter_owned(client, member_user, member_headers, sample_list, shared_list):
    """filter=owned returns only lists the user owns."""
    response = client.get("/lists?filter=owned", headers=member_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Member's Wishlist"


def test_list_lists_filter_shared(client, admin_user, admin_headers, shared_list):
    """filter=shared returns only lists shared with the user (not owned)."""
    response = client.get("/lists?filter=shared", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Member's Wishlist"


def test_list_lists_filter_shared_excludes_owned(client, member_user, member_headers, sample_list):
    """filter=shared does not return owned lists."""
    response = client.get("/lists?filter=shared", headers=member_headers)
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_get_list_as_owner(client, member_user, member_headers, sample_list):
    response = client.get(f"/lists/{sample_list.id}", headers=member_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Member's Wishlist"
    assert "gifts" in data


def test_get_list_as_shared_user(client, admin_user, admin_headers, shared_list):
    response = client.get(f"/lists/{shared_list.id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Member's Wishlist"


def test_get_list_forbidden(client, admin_user, admin_headers, sample_list):
    response = client.get(f"/lists/{sample_list.id}", headers=admin_headers)
    assert response.status_code == 403


def test_get_list_not_found(client, member_headers):
    response = client.get("/lists/99999", headers=member_headers)
    assert response.status_code == 404


def test_update_list_as_owner(client, member_headers, sample_list):
    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={"name": "Updated Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


def test_update_list_as_shared_user(client, admin_headers, shared_list):
    response = client.put(
        f"/lists/{shared_list.id}",
        headers=admin_headers,
        json={"name": "Hacked"},
    )
    assert response.status_code == 403


def test_delete_list_as_owner(client, member_headers, sample_list):
    response = client.delete(f"/lists/{sample_list.id}", headers=member_headers)
    assert response.status_code == 204


def test_delete_list_as_shared_user(client, admin_headers, shared_list):
    response = client.delete(f"/lists/{shared_list.id}", headers=admin_headers)
    assert response.status_code == 403


def test_archive_list(client, member_headers, sample_list):
    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={"is_archived": True},
    )
    assert response.status_code == 200
    assert response.json()["is_archived"] is True


def test_list_excludes_archived_by_default(client, member_headers, sample_list, db):
    sample_list.is_archived = True
    db.flush()

    response = client.get("/lists?filter=owned", headers=member_headers)
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_list_archived_filter(client, member_headers, sample_list, db):
    sample_list.is_archived = True
    db.flush()

    response = client.get("/lists?filter=owned&archived=true", headers=member_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["is_archived"] is True


def test_filter_shared_returns_both_paths(client, family_world):
    """One scope: lists shared directly AND lists granted through a family."""
    w = family_world
    resp = client.get("/lists?filter=shared", headers=_auth(w.u))
    assert resp.status_code == 200
    names = {l["name"] for l in resp.json()}
    assert names == {"P's List", "Q's List"}
    assert "U's List" not in names  # own list excluded
    assert "P's Archived" not in names  # archived excluded by default


def test_filter_shared_reports_the_occasion_route_with_its_family(
    client, family_world
):
    """The occasion arm carries its family alongside it — the viewer needs both
    to make sense of the route."""
    w = family_world
    row = next(
        l for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
        if l["name"] == "Q's List"
    )
    assert row["shared_via"] == [
        {
            "kind": "occasion",
            "occasion": {"id": w.o2.id, "name": "F2 Christmas"},
            "family": {"id": w.f2.id, "name": "F2 Family"},
        }
    ]


def test_filter_shared_returns_one_row_however_many_routes_it_has(
    client, family_world
):
    """L_p is shared directly with U *and* to two occasions U can reach. The row
    is still one row — it is the routes that are plural, not the list."""
    w = family_world
    rows = [
        l for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
        if l["name"] == "P's List"
    ]
    assert len(rows) == 1
    assert len(rows[0]["shared_via"]) == 3


def test_filter_shared_reports_both_occasions_each_with_its_own_family(
    client, family_world, db
):
    """P's List is shared to an occasion in each of U's families. Both routes
    come back, and each names the family behind its own occasion."""
    w = family_world
    db.query(ListShare).filter(ListShare.list_id == w.l_p.id).delete()
    db.flush()

    rows = [
        l for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
        if l["name"] == "P's List"
    ]
    assert len(rows) == 1
    assert rows[0]["shared_via"] == [
        {
            "kind": "occasion",
            "occasion": {"id": w.o1.id, "name": "F1 Christmas"},
            "family": {"id": w.f1.id, "name": "F1 Family"},
        },
        {
            "kind": "occasion",
            "occasion": {"id": w.o2.id, "name": "F2 Christmas"},
            "family": {"id": w.f2.id, "name": "F2 Family"},
        },
    ]


def test_filter_shared_direct_only_list_reports_one_direct_route(
    client, admin_user, admin_headers, shared_list, member_user
):
    """The direct arm names the list's owner. Redundant with `owner_name` on
    purpose: `shared_via` is the authoritative statement of how a list arrived,
    and the client reads attribution off it alone."""
    data = client.get("/lists?filter=shared", headers=admin_headers).json()
    assert len(data) == 1
    assert data[0]["shared_via"] == [
        {
            "kind": "direct",
            "person": {"id": member_user.id, "name": member_user.name},
        }
    ]


def test_filter_shared_excludes_own_list_shared_to_own_occasion(
    client, family_world, db
):
    """U shares their own list to an occasion U can reach: still not shared
    *with* U."""
    w = family_world
    db.add(ListOccasionShare(list_id=w.l_u.id, occasion_id=w.o1.id))
    db.flush()

    names = {
        l["name"] for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
    }
    assert "U's List" not in names


def test_filter_shared_archived_returns_archived_only(client, family_world):
    w = family_world
    resp = client.get("/lists?filter=shared&archived=true", headers=_auth(w.u))
    assert resp.status_code == 200
    data = resp.json()
    assert {l["name"] for l in data} == {"P's Archived"}
    assert data[0]["shared_via"] == [
        {
            "kind": "occasion",
            "occasion": {"id": w.o1.id, "name": "F1 Christmas"},
            "family": {"id": w.f1.id, "name": "F1 Family"},
        }
    ]


def test_filter_shared_drops_a_list_whose_occasion_share_was_revoked(
    client, family_world, db
):
    w = family_world
    db.query(ListOccasionShare).filter(
        ListOccasionShare.list_id == w.l_q.id
    ).delete()
    db.flush()

    names = {
        l["name"] for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
    }
    assert "Q's List" not in names


def test_filter_shared_keeps_a_list_whose_occasion_was_archived(
    client, family_world, db
):
    """Archiving blocks new shares and nothing else, so the list stays in the
    shared scope, still labelled with the occasion it arrived through."""
    w = family_world
    w.o2.is_archived = True
    db.flush()

    row = next(
        l for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
        if l["name"] == "Q's List"
    )
    assert [r["occasion"]["id"] for r in row["shared_via"]] == [w.o2.id]


def test_filter_shared_orders_most_recently_updated_first(client, family_world):
    w = family_world
    data = client.get("/lists?filter=shared", headers=_auth(w.u)).json()
    assert [l["updated_at"] for l in data] == sorted(
        (l["updated_at"] for l in data), reverse=True
    )


def test_filter_shared_empty_for_a_user_with_no_shares(client, member_headers):
    resp = client.get("/lists?filter=shared", headers=member_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_owned_lists_carry_an_empty_route_list(client, member_headers, sample_list):
    """An owned row reached the caller no way at all — an empty array, asserted
    as an array. `shared_via` is never absent and never null."""
    resp = client.get("/lists?filter=owned", headers=member_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["shared_via"] == []


def test_filter_family_is_gone(client, member_headers):
    """The separate family scope was folded into ?filter=shared."""
    resp = client.get("/lists?filter=family", headers=member_headers)
    assert resp.status_code == 422


# --- recipient fields (NEU-1216) ---


def test_create_list_with_recipient(client, member_user, member_headers):
    response = client.post(
        "/lists",
        headers=member_headers,
        json={
            "name": "Christmas Ideas",
            "recipient_name": "Beth",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["recipient_name"] == "Beth"
    assert "recipient_has_account" not in data
    assert data["owner_id"] == member_user.id


def test_create_list_without_recipient_leaves_it_null(client, member_headers):
    response = client.post(
        "/lists", headers=member_headers, json={"name": "My own list"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["recipient_name"] is None


def test_create_list_normalizes_recipient_name(client, member_headers):
    response = client.post(
        "/lists",
        headers=member_headers,
        json={"name": "L", "recipient_name": " Beth "},
    )
    assert response.status_code == 201
    assert response.json()["recipient_name"] == "Beth"


def test_create_list_whitespace_recipient_name_becomes_null(client, member_headers):
    response = client.post(
        "/lists", headers=member_headers, json={"name": "L", "recipient_name": "   "}
    )
    assert response.status_code == 201
    assert response.json()["recipient_name"] is None


def test_update_list_sets_recipient(client, member_headers, sample_list):
    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={"recipient_name": "Jane"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["recipient_name"] == "Jane"


def test_update_list_clears_recipient(client, member_headers, sample_list, db):
    sample_list.recipient_name = "Beth"
    db.flush()

    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={"recipient_name": None},
    )
    assert response.status_code == 200
    assert response.json()["recipient_name"] is None


def test_update_list_name_only_leaves_recipient_untouched(
    client, member_headers, sample_list, db
):
    sample_list.recipient_name = "Beth"
    db.flush()

    response = client.put(
        f"/lists/{sample_list.id}", headers=member_headers, json={"name": "Renamed"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Renamed"
    assert data["recipient_name"] == "Beth"


def test_list_folder_endpoint_returns_recipient_fields(
    client, member_headers, sample_list, db
):
    # compute_counts builds an explicit dict; a missing key silently nulls the field.
    sample_list.recipient_name = "Beth"
    db.flush()

    response = client.get("/lists?filter=owned", headers=member_headers)
    assert response.status_code == 200
    row = response.json()[0]
    assert row["recipient_name"] == "Beth"
    assert "recipient_has_account" not in row


def test_owner_detail_returns_recipient_fields(
    client, member_headers, sample_list, db
):
    sample_list.recipient_name = "Beth"
    db.flush()

    response = client.get(f"/lists/{sample_list.id}", headers=member_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["recipient_name"] == "Beth"
    assert "recipient_has_account" not in data


def test_viewer_detail_returns_recipient_fields(
    client, admin_headers, shared_list, db
):
    shared_list.recipient_name = "Beth"
    db.flush()

    response = client.get(f"/lists/{shared_list.id}", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["recipient_name"] == "Beth"
    assert "recipient_has_account" not in data


# --- account people on lists (NEU-1228) ---


@pytest.fixture
def account_people(client, member_headers):
    """The member account marked shared, with Gran and Grandpa on it."""
    response = client.put(
        "/account",
        headers=member_headers,
        json={
            "is_shared_account": True,
            "people": [{"name": "Gran"}, {"name": "Grandpa"}],
        },
    )
    assert response.status_code == 200
    return response.json()["people"]


def test_create_list_with_account_person(client, member_headers, account_people):
    gran = account_people[0]
    response = client.post(
        "/lists",
        headers=member_headers,
        json={"name": "Gran's List", "account_person_id": gran["id"]},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["account_person_id"] == gran["id"]
    assert data["account_person_name"] == "Gran"


def test_create_list_with_neither_person_nor_recipient(
    client, member_headers, account_people
):
    # §4.2: a shared account may own a household list — "ideas for the kitchen"
    # is for neither person, and the API does not demand an answer.
    response = client.post(
        "/lists", headers=member_headers, json={"name": "Ideas for the Kitchen"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["account_person_id"] is None
    assert data["recipient_name"] is None


def test_create_list_with_person_and_recipient_is_400(
    client, member_headers, account_people
):
    response = client.post(
        "/lists",
        headers=member_headers,
        json={
            "name": "Confused",
            "account_person_id": account_people[0]["id"],
            "recipient_name": "Beth",
        },
    )
    assert response.status_code == 400


def test_create_list_with_another_accounts_person_is_404(
    client, admin_headers, account_people
):
    response = client.post(
        "/lists",
        headers=admin_headers,
        json={"name": "Not mine", "account_person_id": account_people[0]["id"]},
    )
    assert response.status_code == 404


def test_update_list_sets_account_person(
    client, member_headers, sample_list, account_people
):
    grandpa = account_people[1]
    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={"account_person_id": grandpa["id"]},
    )
    assert response.status_code == 200
    assert response.json()["account_person_name"] == "Grandpa"


def test_update_list_clears_account_person_with_explicit_null(
    client, db, member_headers, sample_list, account_people
):
    sample_list.account_person_id = account_people[0]["id"]
    db.flush()

    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={"account_person_id": None},
    )
    assert response.status_code == 200
    assert response.json()["account_person_id"] is None


def test_update_list_leaves_account_person_alone_when_omitted(
    client, db, member_headers, sample_list, account_people
):
    sample_list.account_person_id = account_people[0]["id"]
    db.flush()

    response = client.put(
        f"/lists/{sample_list.id}", headers=member_headers, json={"name": "Renamed"}
    )
    assert response.status_code == 200
    assert response.json()["account_person_id"] == account_people[0]["id"]


def test_adding_a_person_to_a_list_with_a_recipient_is_400(
    client, db, member_headers, sample_list, account_people
):
    # The stored state is what makes this illegal, and only the service can see it.
    sample_list.recipient_name = "Beth"
    db.flush()

    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={"account_person_id": account_people[0]["id"]},
    )
    assert response.status_code == 400


def test_adding_a_recipient_to_a_list_with_a_person_is_400(
    client, db, member_headers, sample_list, account_people
):
    sample_list.account_person_id = account_people[0]["id"]
    db.flush()

    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={"recipient_name": "Beth"},
    )
    assert response.status_code == 400


def test_clearing_one_then_setting_the_other_is_allowed(
    client, db, member_headers, sample_list, account_people
):
    sample_list.recipient_name = "Beth"
    db.flush()

    response = client.put(
        f"/lists/{sample_list.id}",
        headers=member_headers,
        json={
            "recipient_name": None,
            "account_person_id": account_people[0]["id"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["recipient_name"] is None
    assert data["account_person_name"] == "Gran"


def test_update_list_with_another_accounts_person_is_404(
    client, db, admin_headers, admin_user, account_people
):
    admins_list = GiftList(name="Admin's List", owner_id=admin_user.id)
    db.add(admins_list)
    db.flush()

    response = client.put(
        f"/lists/{admins_list.id}",
        headers=admin_headers,
        json={"account_person_id": account_people[0]["id"]},
    )
    assert response.status_code == 404


def test_list_collection_returns_account_person_fields(
    client, db, member_headers, sample_list, account_people
):
    # compute_counts builds an explicit dict; a missing key silently nulls the field.
    sample_list.account_person_id = account_people[0]["id"]
    db.flush()

    row = client.get("/lists?filter=owned", headers=member_headers).json()[0]
    assert row["account_person_id"] == account_people[0]["id"]
    assert row["account_person_name"] == "Gran"


def test_owner_detail_returns_account_person_fields(
    client, db, member_headers, sample_list, account_people
):
    sample_list.account_person_id = account_people[0]["id"]
    db.flush()

    data = client.get(f"/lists/{sample_list.id}", headers=member_headers).json()
    assert data["account_person_id"] == account_people[0]["id"]
    assert data["account_person_name"] == "Gran"


def test_viewer_detail_returns_account_person_fields(
    client, db, admin_headers, shared_list, account_people
):
    # A family member browsing a shared account's lists sees "for Gran" — that
    # is the whole point of labelling them, and it discloses nothing the
    # account has not chosen to publish.
    shared_list.account_person_id = account_people[0]["id"]
    db.flush()

    data = client.get(f"/lists/{shared_list.id}", headers=admin_headers).json()
    assert data["account_person_id"] == account_people[0]["id"]
    assert data["account_person_name"] == "Gran"


def test_list_without_a_person_reports_both_fields_null(
    client, member_headers, sample_list
):
    data = client.get(f"/lists/{sample_list.id}", headers=member_headers).json()
    assert data["account_person_id"] is None
    assert data["account_person_name"] is None


# --- unpurchased-claims count on shared rows (NEU-1279) ---
#
# The `• N to buy` badge on the Lists dashboard (project spec §9.1). For a
# directly shared list it is the *only* route to the claim — that claim files
# under no occasion and, unless the list sits in a folder, appears on no
# shopping tab at all (§9.4) — so it is required, not decorative.


@pytest.fixture
def shopping_world(db, family_world):
    """`family_world`, with claims on it: U has one gift still to buy on L_p and
    one on L_q, has already bought a second on L_p, and Q has claimed a third
    that is none of U's business."""
    from datetime import datetime, timezone

    from app.models.claim import Claim
    from app.models.gift import Gift

    w = family_world
    to_buy, bought, qs, spare = (
        Gift(list_id=w.l_p.id, name="To buy"),
        Gift(list_id=w.l_p.id, name="Bought"),
        Gift(list_id=w.l_p.id, name="Q's pick"),
        Gift(list_id=w.l_p.id, name="Unclaimed"),
    )
    on_l_q = Gift(list_id=w.l_q.id, name="To buy on Q's list")
    db.add_all([to_buy, bought, qs, spare, on_l_q])
    db.flush()

    now = datetime.now(timezone.utc)
    db.add_all(
        [
            Claim(gift_id=to_buy.id, user_id=w.u.id, claimed_at=now),
            Claim(gift_id=bought.id, user_id=w.u.id, claimed_at=now, purchased_at=now),
            Claim(gift_id=qs.id, user_id=w.q.id, claimed_at=now),
            Claim(gift_id=on_l_q.id, user_id=w.u.id, claimed_at=now),
        ]
    )
    db.flush()
    return w


def _row(response, list_id):
    return next(row for row in response.json() if row["id"] == list_id)


def test_shared_row_counts_the_callers_own_unpurchased_claims(client, shopping_world):
    w = shopping_world
    response = client.get("/lists?filter=shared", headers=_auth(w.u))
    assert response.status_code == 200
    row = _row(response, w.l_p.id)
    # Three of L_p's four gifts are claimed; one of those is U's and unbought.
    assert row["claimed_count"] == 3
    assert row["my_unpurchased_claim_count"] == 1


def test_a_purchased_claim_is_not_still_to_buy(client, db, shopping_world):
    """Ticking a gift bought is what clears it off the badge."""
    from datetime import datetime, timezone

    from app.models.claim import Claim
    from app.models.gift import Gift

    w = shopping_world
    still_to_buy = (
        db.query(Claim)
        .join(Gift, Gift.id == Claim.gift_id)
        .filter(Gift.list_id == w.l_p.id, Claim.user_id == w.u.id,
                Claim.purchased_at.is_(None))
        .one()
    )
    still_to_buy.purchased_at = datetime.now(timezone.utc)
    db.flush()

    response = client.get("/lists?filter=shared", headers=_auth(w.u))
    assert _row(response, w.l_p.id)["my_unpurchased_claim_count"] == 0
    # The list is no less spoken for, though — the two counts answer different
    # questions and only one of them is about the caller.
    assert _row(response, w.l_p.id)["claimed_count"] == 3


def test_another_viewers_claims_are_not_mine_to_buy(client, shopping_world):
    """Q claimed a gift on L_p; U shares F2 with Q and can see the list. The
    badge counts what *U* has to buy, never what anyone else has taken."""
    w = shopping_world
    response = client.get("/lists?filter=shared", headers=_auth(w.q))
    row = _row(response, w.l_p.id)
    assert row["claimed_count"] == 3
    assert row["my_unpurchased_claim_count"] == 1


def test_the_count_is_per_row_not_per_scope(client, shopping_world):
    """Two shared lists, one claim of U's outstanding on each: each row reports
    its own, not the scope's total."""
    w = shopping_world
    response = client.get("/lists?filter=shared", headers=_auth(w.u))
    assert _row(response, w.l_q.id)["my_unpurchased_claim_count"] == 1


def test_a_shared_row_with_no_claims_of_mine_reports_zero(client, shopping_world):
    w = shopping_world
    response = client.get("/lists?filter=shared&archived=true", headers=_auth(w.u))
    assert _row(response, w.l_p_arch.id)["my_unpurchased_claim_count"] == 0


def test_the_unfiltered_scope_carries_the_count_on_shared_rows_only(
    client, shopping_world
):
    """`GET /lists` mixes owned and shared rows. U owns L_u, which must not
    carry the field at all — the same rule `claimed_count` broke (ADR 0003)."""
    w = shopping_world
    response = client.get("/lists", headers=_auth(w.u))
    assert response.status_code == 200
    assert "my_unpurchased_claim_count" not in _row(response, w.l_u.id)
    shared = _row(response, w.l_p.id)
    assert shared["my_unpurchased_claim_count"] == 1


def test_the_count_costs_no_query_per_row(client, db, shopping_world):
    """The badge must not reintroduce an N+1 across the shared scope: whatever
    `GET /lists?filter=shared` costs, it costs the same for several times the
    rows. The added lists carry claimed gifts of their own, so this pins the
    batching of `Gift.claim` as well as of `GiftList.gifts` — a count queried
    per gift would slip past rows that had none."""
    from datetime import datetime, timezone

    from sqlalchemy import event

    from app.models.claim import Claim
    from app.models.gift import Gift
    from app.models.gift_list import GiftList
    from app.models.list_occasion_share import ListOccasionShare

    w = shopping_world
    engine = db.get_bind()

    def count_queries():
        seen = []

        @event.listens_for(engine, "before_cursor_execute")
        def record(conn, cursor, statement, *args):
            seen.append(statement)

        try:
            response = client.get("/lists?filter=shared", headers=_auth(w.u))
            assert response.status_code == 200
            return len(seen), len(response.json())
        finally:
            event.remove(engine, "before_cursor_execute", record)

    before, rows_before = count_queries()

    # Six more lists in the same scope, each shared to an occasion U can reach
    # and each carrying two gifts U has claimed and not yet bought.
    now = datetime.now(timezone.utc)
    for n in range(6):
        extra = GiftList(name=f"Extra {n}", owner_id=w.p.id)
        db.add(extra)
        db.flush()
        db.add(ListOccasionShare(list_id=extra.id, occasion_id=w.o1.id))
        for m in range(2):
            gift = Gift(list_id=extra.id, name=f"Extra {n} gift {m}")
            db.add(gift)
            db.flush()
            db.add(Claim(gift_id=gift.id, user_id=w.u.id, claimed_at=now))
    db.flush()

    after, rows_after = count_queries()
    assert rows_after == rows_before + 6, "the extra lists should be in scope"
    assert after == before, (
        f"query count grew with the row count ({before} → {after}): "
        "the count is being computed per row"
    )


def test_the_badge_reaches_a_claim_on_a_directly_shared_list(client, db, family_world):
    """The case §9.4 makes the badge mandatory for. A claim on a list shared
    only person-to-person files under no occasion and, with the list in no
    folder, appears on no shopping tab at all — this row is its only route.

    Deliberately not `shopping_world`'s L_p, which is *also* occasion-shared and
    so would pass on the occasion path alone.
    """
    from datetime import datetime, timezone

    from app.models.claim import Claim
    from app.models.gift import Gift
    from app.models.list_share import ListShare

    w = family_world
    direct_only = GiftList(name="Jane's Wishlist", owner_id=w.q.id)
    db.add(direct_only)
    db.flush()
    db.add(ListShare(list_id=direct_only.id, user_id=w.u.id))
    gift = Gift(list_id=direct_only.id, name="Cast iron skillet")
    db.add(gift)
    db.flush()
    db.add(
        Claim(
            gift_id=gift.id,
            user_id=w.u.id,
            occasion_id=None,  # no occasion: this is the gap the badge covers
            claimed_at=datetime.now(timezone.utc),
        )
    )
    db.flush()

    response = client.get("/lists?filter=shared", headers=_auth(w.u))
    assert response.status_code == 200
    row = _row(response, direct_only.id)
    assert [r["kind"] for r in row["shared_via"]] == [
        "direct"
    ], "this list is reachable no other way"
    assert row["my_unpurchased_claim_count"] == 1


def test_filter_shared_reports_both_routes_for_a_both_ways_list(client, family_world):
    """L_p reaches U directly *and* through two occasions. Every route is
    reported — the discard is the regression this project exists to fix."""
    w = family_world
    rows = [
        l for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
        if l["name"] == "P's List"
    ]
    assert len(rows) == 1
    assert rows[0]["shared_via"] == [
        {"kind": "direct", "person": {"id": w.p.id, "name": "Owner P"}},
        {
            "kind": "occasion",
            "occasion": {"id": w.o1.id, "name": "F1 Christmas"},
            "family": {"id": w.f1.id, "name": "F1 Family"},
        },
        {
            "kind": "occasion",
            "occasion": {"id": w.o2.id, "name": "F2 Christmas"},
            "family": {"id": w.f2.id, "name": "F2 Family"},
        },
    ]


def test_filter_shared_orders_routes_direct_first_then_by_occasion_id(
    client, family_world
):
    """A literal, and the same literal twice: the order exists so a response is
    byte-stable across requests, not so the client can read `routes[0]`."""
    w = family_world

    def routes():
        return next(
            l for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
            if l["name"] == "P's List"
        )["shared_via"]

    first = routes()
    assert [
        (r["kind"], r.get("occasion", {}).get("id")) for r in first
    ] == [("direct", None), ("occasion", w.o1.id), ("occasion", w.o2.id)]
    assert routes() == first


def test_unfiltered_lists_includes_an_occasion_only_shared_list(client, family_world):
    """The unfiltered scope is `can_view_list`'s three terms, the occasion one
    included. It matched owner-OR-`ListShare` only, so it disagreed with the
    codebase's one visibility predicate (`CONTEXT.md` invariant 2)."""
    w = family_world
    names = {l["name"] for l in client.get("/lists", headers=_auth(w.u)).json()}
    assert "Q's List" in names, "reaches U only through F2's occasion"
    assert names == {"U's List", "P's List", "Q's List"}


def test_the_same_list_carries_the_same_routes_on_every_surface(
    client, family_world, db
):
    """`/lists`, a folder page and an occasion page all return list rows, and
    they must agree about how a list arrived — NEU-1286's "same attribution on
    /lists and on a folder page" is exactly this."""
    w = family_world
    folder = Folder(name="Christmas 2026", owner_id=w.u.id)
    db.add(folder)
    db.flush()
    db.add(FolderItem(folder_id=folder.id, list_id=w.l_p.id))
    db.flush()

    def routes_from(payload):
        return next(row for row in payload if row["id"] == w.l_p.id)["shared_via"]

    headers = _auth(w.u)
    on_lists = routes_from(client.get("/lists?filter=shared", headers=headers).json())
    on_folder = routes_from(
        client.get(f"/folders/{folder.id}", headers=headers).json()["lists"]
    )
    on_occasion = routes_from(
        client.get(f"/occasions/{w.o1.id}/lists", headers=headers).json()
    )

    assert len(on_lists) == 3
    assert on_folder == on_lists
    assert on_occasion == on_lists


def test_a_folder_drops_a_list_whose_share_was_revoked(client, family_world, db):
    """Revoking a share does not remove folder items, so a `folder_items` row
    can outlive the grant behind it. The folder reads through `can_view_list`,
    so the row is gone rather than served with no attribution at all."""
    w = family_world
    folder = Folder(name="Christmas 2026", owner_id=w.u.id)
    db.add(folder)
    db.flush()
    db.add_all(
        [
            FolderItem(folder_id=folder.id, list_id=w.l_p.id),
            FolderItem(folder_id=folder.id, list_id=w.l_q.id),
        ]
    )
    db.flush()

    # Q's List reached U only through F2's occasion. Withdraw it.
    db.query(ListOccasionShare).filter(
        ListOccasionShare.list_id == w.l_q.id
    ).delete()
    db.flush()

    rows = client.get(f"/folders/{folder.id}", headers=_auth(w.u)).json()["lists"]
    assert [row["id"] for row in rows] == [w.l_p.id]


def test_shared_scope_costs_no_query_per_row(client, family_world, db):
    """The routes are fetched for the whole page in one query, so the response
    does not cost a query per row as the shared scope grows."""
    from sqlalchemy import event

    w = family_world
    engine = db.get_bind()

    def count_queries():
        seen = []

        @event.listens_for(engine, "before_cursor_execute")
        def record(conn, cursor, statement, *args):
            seen.append(statement)

        try:
            resp = client.get("/lists?filter=shared", headers=_auth(w.u))
            assert resp.status_code == 200
            return len(seen), len(resp.json())
        finally:
            event.remove(engine, "before_cursor_execute", record)

    before, rows_before = count_queries()

    # Six more lists of Q's, each shared to F2's occasion, so each arrives with
    # a route of its own to assemble.
    for n in range(6):
        extra = GiftList(name=f"Q's Extra {n}", owner_id=w.q.id)
        db.add(extra)
        db.flush()
        db.add(ListOccasionShare(list_id=extra.id, occasion_id=w.o2.id))
    db.flush()

    after, rows_after = count_queries()
    assert rows_after == rows_before + 6, "the extra lists should be in scope"
    assert after == before, (
        f"query count grew with the row count ({before} → {after}): "
        "the routes are being fetched per row"
    )


def test_owned_lists_cost_no_route_query_at_all(client, family_world, db):
    """Every row on `?filter=owned` is the caller's own, and an owned row cannot
    carry a route — so the page asks about routes not once, rather than once for
    an answer it already knows."""
    from sqlalchemy import event

    w = family_world
    engine = db.get_bind()
    seen = []

    @event.listens_for(engine, "before_cursor_execute")
    def record(conn, cursor, statement, *args):
        seen.append(statement)

    try:
        resp = client.get("/lists?filter=owned", headers=_auth(w.u))
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert resp.status_code == 200
    assert [row["shared_via"] for row in resp.json()] == [[]]
    assert not [s for s in seen if "list_occasion_shares" in s], (
        "the owned page ran a share-route query, which can only return nothing"
    )
