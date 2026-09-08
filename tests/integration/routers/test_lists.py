from types import SimpleNamespace

import pytest

from app.dependencies import create_access_token
from app.models.family import Family
from app.models.family_member import FamilyMember
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


def test_filter_shared_labels_an_occasion_only_list_with_its_occasion(
    client, family_world
):
    """The occasion arm carries its family alongside it — the viewer needs both
    to make sense of the label."""
    w = family_world
    row = next(
        l for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
        if l["name"] == "Q's List"
    )
    assert row["shared_via"] == {
        "kind": "occasion",
        "id": w.o2.id,
        "name": "F2 Christmas",
        "family": {"id": w.f2.id, "name": "F2 Family"},
    }


def test_filter_shared_dedupes_both_paths_to_the_direct_share(client, family_world):
    """L_p is shared directly with U *and* to two occasions U can reach: one row,
    labelled with the owner, because the direct share is the more specific fact."""
    w = family_world
    rows = [
        l for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
        if l["name"] == "P's List"
    ]
    assert len(rows) == 1
    assert rows[0]["shared_via"] == {
        "kind": "user",
        "id": w.p.id,
        "name": "Owner P",
        "family": None,
    }


def test_filter_shared_dedupes_a_list_shared_to_two_occasions(client, family_world, db):
    """P's List is shared to an occasion in each of U's families. Without the
    direct share it is still one row, carrying one of them."""
    w = family_world
    db.query(ListShare).filter(ListShare.list_id == w.l_p.id).delete()
    db.flush()

    rows = [
        l for l in client.get("/lists?filter=shared", headers=_auth(w.u)).json()
        if l["name"] == "P's List"
    ]
    assert len(rows) == 1
    assert rows[0]["shared_via"]["kind"] == "occasion"
    # The lower occasion id wins — arbitrary, but stable, so the label does not
    # flicker between requests.
    assert rows[0]["shared_via"]["id"] == min(w.o1.id, w.o2.id)


def test_filter_shared_direct_only_list_is_labelled_with_its_owner(
    client, admin_user, admin_headers, shared_list, member_user
):
    data = client.get("/lists?filter=shared", headers=admin_headers).json()
    assert len(data) == 1
    assert data[0]["shared_via"] == {
        "kind": "user",
        "id": member_user.id,
        "name": member_user.name,
        "family": None,
    }


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
    assert data[0]["shared_via"] == {
        "kind": "occasion",
        "id": w.o1.id,
        "name": "F1 Christmas",
        "family": {"id": w.f1.id, "name": "F1 Family"},
    }


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
    assert row["shared_via"]["id"] == w.o2.id


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


def test_owned_lists_carry_no_shared_via(client, member_headers, sample_list):
    resp = client.get("/lists?filter=owned", headers=member_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["shared_via"] is None


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
