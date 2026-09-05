from types import SimpleNamespace

import pytest

from app.dependencies import create_access_token
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift_list import GiftList
from app.models.list_family_share import ListFamilyShare
from app.models.list_share import ListShare
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

    db.add(ListShare(list_id=l_p.id, user_id=u.id))  # L_p also manually shared with U
    # Family visibility is an explicit per-(list, family) grant. These mirror what
    # the owners would have opted into: P shares with both families, Q with F2.
    db.add_all(
        [
            ListFamilyShare(list_id=l_p.id, family_id=f1.id),
            ListFamilyShare(list_id=l_p.id, family_id=f2.id),
            ListFamilyShare(list_id=l_p_arch.id, family_id=f1.id),
            ListFamilyShare(list_id=l_q.id, family_id=f2.id),
        ]
    )
    db.flush()

    return SimpleNamespace(
        u=u, p=p, q=q, f1=f1, f2=f2, l_u=l_u, l_p=l_p, l_p_arch=l_p_arch, l_q=l_q
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


def test_filter_family_returns_comembers_active_lists(client, family_world):
    w = family_world
    resp = client.get("/lists?filter=family", headers=_auth(w.u))
    assert resp.status_code == 200
    names = {l["name"] for l in resp.json()}
    assert names == {"P's List", "Q's List"}  # co-members' active lists only
    assert "U's List" not in names  # own list excluded
    assert "P's Archived" not in names  # archived excluded by default


def test_filter_family_annotates_all_shared_families(client, family_world):
    w = family_world
    data = {l["name"]: l for l in client.get(
        "/lists?filter=family", headers=_auth(w.u)
    ).json()}
    # P shares both F1 and F2 with U -> P's list annotated with both (order-agnostic).
    assert sorted(f["name"] for f in data["P's List"]["families"]) == [
        "F1 Family",
        "F2 Family",
    ]
    # Q shares only F2 with U.
    assert sorted(f["name"] for f in data["Q's List"]["families"]) == ["F2 Family"]


def test_filter_family_includes_list_also_manually_shared(client, family_world):
    w = family_world
    fam = {l["name"] for l in client.get(
        "/lists?filter=family", headers=_auth(w.u)
    ).json()}
    shared = {l["name"] for l in client.get(
        "/lists?filter=shared", headers=_auth(w.u)
    ).json()}
    assert "P's List" in fam  # appears under family
    assert "P's List" in shared  # AND under shared (independent views)


def test_filter_family_archived_returns_archived_only(client, family_world):
    w = family_world
    resp = client.get("/lists?filter=family&archived=true", headers=_auth(w.u))
    assert resp.status_code == 200
    assert {l["name"] for l in resp.json()} == {"P's Archived"}


def test_filter_family_empty_for_non_member(client, member_user, member_headers):
    # member_user belongs to no family.
    resp = client.get("/lists?filter=family", headers=member_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_filter_shared_has_empty_families_annotation(client, family_world):
    w = family_world
    resp = client.get("/lists?filter=shared", headers=_auth(w.u))
    assert resp.status_code == 200
    for l in resp.json():
        assert l["families"] == []


def test_filter_invalid_value_rejected(client, member_headers):
    resp = client.get("/lists?filter=bogus", headers=member_headers)
    assert resp.status_code == 422
