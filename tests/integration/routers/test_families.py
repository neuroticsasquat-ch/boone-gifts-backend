import pytest
from fastapi import status
from sqlalchemy import select

from app.dependencies import create_access_token
from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.models.user import User


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def second_user(db):
    user = User(email="second@test.com", name="Second", role="member", password_hash="x")
    user.set_password("second123")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def second_headers(second_user):
    token = create_access_token(second_user)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def family(db, member_user):
    """A family owned (and organized) by member_user."""
    fam = Family(name="Boone Family", created_by_id=member_user.id)
    db.add(fam)
    db.flush()
    organizer = FamilyMember(family_id=fam.id, user_id=member_user.id, role="organizer")
    db.add(organizer)
    db.flush()
    return fam


@pytest.fixture
def family_with_second_member(db, family, second_user):
    """Adds second_user as a plain member of `family`."""
    member = FamilyMember(family_id=family.id, user_id=second_user.id, role="member")
    db.add(member)
    db.flush()
    return family


@pytest.fixture
def family_with_second_organizer(db, family, second_user):
    """Adds second_user as a second organizer of `family`."""
    member = FamilyMember(family_id=family.id, user_id=second_user.id, role="organizer")
    db.add(member)
    db.flush()
    return family


@pytest.fixture
def third_user(db):
    user = User(email="third@test.com", name="Third", role="member", password_hash="x")
    user.set_password("third123")
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _seed_cross_artifacts(db, user_a, user_b):
    """Reciprocal claims + collection items between two users.
    Returns (gift_on_a_claimed_by_b, gift_on_b_claimed_by_a, item_a, item_b)."""
    list_a = GiftList(name=f"{user_a.id}'s List", owner_id=user_a.id)
    list_b = GiftList(name=f"{user_b.id}'s List", owner_id=user_b.id)
    db.add_all([list_a, list_b])
    db.flush()

    gift_a = Gift(list_id=list_a.id, name="On A's list", claimed_by_id=user_b.id)
    gift_b = Gift(list_id=list_b.id, name="On B's list", claimed_by_id=user_a.id)
    db.add_all([gift_a, gift_b])
    db.flush()

    coll_a = Collection(name=f"{user_a.id}'s Collection", owner_id=user_a.id)
    coll_b = Collection(name=f"{user_b.id}'s Collection", owner_id=user_b.id)
    db.add_all([coll_a, coll_b])
    db.flush()

    item_a = CollectionItem(collection_id=coll_a.id, list_id=list_b.id)
    item_b = CollectionItem(collection_id=coll_b.id, list_id=list_a.id)
    db.add_all([item_a, item_b])
    db.flush()

    return gift_a, gift_b, item_a, item_b


def _is_claimed(db, gift):
    row = db.execute(
        select(Gift.claimed_by_id).where(Gift.id == gift.id)
    ).scalar_one_or_none()
    return row is not None


def _item_exists(db, item_id):
    return db.execute(
        select(CollectionItem).where(CollectionItem.id == item_id)
    ).scalar_one_or_none() is not None


def _accept_connection(db, user_a, user_b):
    from app.models.connection import Connection  # not moved: only used here

    conn = Connection(requester_id=user_a.id, addressee_id=user_b.id, status="accepted")
    db.add(conn)
    db.flush()
    return conn


# ---------------------------------------------------------------------------
# POST /families
# ---------------------------------------------------------------------------


def test_create_family_returns_201_with_detail(client, member_headers, member_user):
    response = client.post("/families", json={"name": "My Family"}, headers=member_headers)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "My Family"
    assert data["created_by_id"] == member_user.id
    assert len(data["members"]) == 1
    assert data["members"][0]["user_id"] == member_user.id
    assert data["members"][0]["role"] == "organizer"


def test_create_family_requires_auth(client):
    response = client.post("/families", json={"name": "My Family"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# GET /families
# ---------------------------------------------------------------------------


def test_list_families_returns_list_with_role_and_count(
    client, member_headers, member_user, family
):
    response = client.get("/families", headers=member_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    item = data[0]
    assert item["id"] == family.id
    assert item["name"] == "Boone Family"
    assert item["role"] == "organizer"
    assert item["member_count"] == 1


def test_list_families_empty_when_no_memberships(client, member_headers):
    response = client.get("/families", headers=member_headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_list_families_requires_auth(client):
    response = client.get("/families")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# GET /families/{family_id}
# ---------------------------------------------------------------------------


def test_get_family_detail_for_member(
    client, second_headers, family_with_second_member
):
    fam = family_with_second_member
    response = client.get(f"/families/{fam.id}", headers=second_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == fam.id
    assert data["name"] == fam.name
    assert len(data["members"]) == 2


def test_get_family_detail_403_for_non_member(
    client, second_headers, family
):
    # second_user is NOT a member of `family`
    response = client.get(f"/families/{family.id}", headers=second_headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_get_family_detail_404_for_nonexistent(client, member_headers):
    response = client.get("/families/99999", headers=member_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_family_detail_requires_auth(client, family):
    response = client.get(f"/families/{family.id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# PUT /families/{family_id}
# ---------------------------------------------------------------------------


def test_rename_family_as_organizer(client, member_headers, family):
    response = client.put(
        f"/families/{family.id}",
        json={"name": "Renamed Family"},
        headers=member_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == "Renamed Family"
    assert data["id"] == family.id


def test_rename_family_403_for_non_organizer(
    client, second_headers, family_with_second_member
):
    # second_user is a plain member, not an organizer
    fam = family_with_second_member
    response = client.put(
        f"/families/{fam.id}",
        json={"name": "Sneaky Rename"},
        headers=second_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_rename_family_404_for_nonexistent(client, member_headers):
    response = client.put(
        "/families/99999",
        json={"name": "Whatever"},
        headers=member_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_rename_family_requires_auth(client, family):
    response = client.put(f"/families/{family.id}", json={"name": "X"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# DELETE /families/{family_id}
# ---------------------------------------------------------------------------


def test_delete_family_as_organizer(client, member_headers, family):
    response = client.delete(f"/families/{family.id}", headers=member_headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # subsequent GET should be 404
    get_response = client.get(f"/families/{family.id}", headers=member_headers)
    assert get_response.status_code == status.HTTP_404_NOT_FOUND


def test_delete_family_403_for_non_organizer(
    client, second_headers, family_with_second_member
):
    fam = family_with_second_member
    response = client.delete(f"/families/{fam.id}", headers=second_headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_delete_family_404_for_nonexistent(client, member_headers):
    response = client.delete("/families/99999", headers=member_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_delete_family_requires_auth(client, family):
    response = client.delete(f"/families/{family.id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# DELETE /families/{family_id}/members/{user_id}
# ---------------------------------------------------------------------------


def test_remove_member_self_leave(
    client, second_headers, second_user, family_with_second_member
):
    fam = family_with_second_member
    response = client.delete(
        f"/families/{fam.id}/members/{second_user.id}", headers=second_headers
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    get_resp = client.get(f"/families/{fam.id}", headers=second_headers)
    assert get_resp.status_code == status.HTTP_403_FORBIDDEN


def test_remove_member_organizer_removes_member(
    client, member_headers, second_user, family_with_second_member
):
    fam = family_with_second_member
    response = client.delete(
        f"/families/{fam.id}/members/{second_user.id}", headers=member_headers
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    detail = client.get(f"/families/{fam.id}", headers=member_headers).json()
    assert len(detail["members"]) == 1


def test_remove_member_organizer_removes_co_organizer(
    client, member_headers, second_user, family_with_second_organizer
):
    fam = family_with_second_organizer
    response = client.delete(
        f"/families/{fam.id}/members/{second_user.id}", headers=member_headers
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_remove_member_organizer_self_leave_with_co_organizer(
    client, member_headers, member_user, family_with_second_organizer
):
    fam = family_with_second_organizer
    response = client.delete(
        f"/families/{fam.id}/members/{member_user.id}", headers=member_headers
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    # second_user is still an organizer, so family still accessible
    get_resp = client.get(f"/families/{fam.id}", headers=member_headers)
    assert get_resp.status_code == status.HTTP_403_FORBIDDEN


def test_remove_member_403_member_removes_other(
    client, second_headers, member_user, family_with_second_member
):
    fam = family_with_second_member
    response = client.delete(
        f"/families/{fam.id}/members/{member_user.id}", headers=second_headers
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_remove_member_403_actor_not_a_member(
    client, second_headers, member_user, family
):
    response = client.delete(
        f"/families/{family.id}/members/{member_user.id}", headers=second_headers
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_remove_member_404_family_missing(client, member_headers, member_user):
    response = client.delete(
        f"/families/99999/members/{member_user.id}", headers=member_headers
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_remove_member_404_target_not_a_member(
    client, member_headers, second_user, family
):
    response = client.delete(
        f"/families/{family.id}/members/{second_user.id}", headers=member_headers
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_remove_member_409_last_organizer(
    client, member_headers, member_user, family_with_second_member
):
    # Sole organizer cannot self-leave while other (non-organizer) members remain —
    # that would leave the family without leadership.
    fam = family_with_second_member
    response = client.delete(
        f"/families/{fam.id}/members/{member_user.id}", headers=member_headers
    )
    assert response.status_code == status.HTTP_409_CONFLICT


def test_remove_member_requires_auth(client, member_user, family):
    response = client.delete(f"/families/{family.id}/members/{member_user.id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# PUT /families/{family_id}/members/{user_id}/role
# ---------------------------------------------------------------------------


def test_update_role_promote_member_to_organizer(
    client, member_headers, second_user, family_with_second_member
):
    fam = family_with_second_member
    response = client.put(
        f"/families/{fam.id}/members/{second_user.id}/role",
        json={"role": "organizer"},
        headers=member_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    roles = {m["user_id"]: m["role"] for m in response.json()["members"]}
    assert roles[second_user.id] == "organizer"


def test_update_role_demote_organizer_to_member(
    client, member_headers, second_user, family_with_second_organizer
):
    fam = family_with_second_organizer
    response = client.put(
        f"/families/{fam.id}/members/{second_user.id}/role",
        json={"role": "member"},
        headers=member_headers,
    )
    assert response.status_code == status.HTTP_200_OK
    roles = {m["user_id"]: m["role"] for m in response.json()["members"]}
    assert roles[second_user.id] == "member"


def test_update_role_422_invalid_role(
    client, member_headers, second_user, family_with_second_member
):
    fam = family_with_second_member
    response = client.put(
        f"/families/{fam.id}/members/{second_user.id}/role",
        json={"role": "superuser"},
        headers=member_headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_update_role_403_non_organizer(
    client, second_headers, member_user, family_with_second_member
):
    fam = family_with_second_member
    response = client.put(
        f"/families/{fam.id}/members/{member_user.id}/role",
        json={"role": "member"},
        headers=second_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_update_role_403_member_updates_own_role(
    client, second_headers, second_user, family_with_second_member
):
    fam = family_with_second_member
    response = client.put(
        f"/families/{fam.id}/members/{second_user.id}/role",
        json={"role": "organizer"},
        headers=second_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_update_role_403_actor_not_a_member(
    client, second_headers, member_user, family
):
    response = client.put(
        f"/families/{family.id}/members/{member_user.id}/role",
        json={"role": "member"},
        headers=second_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_update_role_404_family_missing(client, member_headers, member_user):
    response = client.put(
        f"/families/99999/members/{member_user.id}/role",
        json={"role": "member"},
        headers=member_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_update_role_404_target_not_a_member(
    client, member_headers, second_user, family
):
    response = client.put(
        f"/families/{family.id}/members/{second_user.id}/role",
        json={"role": "organizer"},
        headers=member_headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_update_role_409_demote_last_organizer(
    client, member_headers, member_user, family
):
    response = client.put(
        f"/families/{family.id}/members/{member_user.id}/role",
        json={"role": "member"},
        headers=member_headers,
    )
    assert response.status_code == status.HTTP_409_CONFLICT


def test_update_role_requires_auth(client, member_user, family):
    response = client.put(
        f"/families/{family.id}/members/{member_user.id}/role",
        json={"role": "member"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# repository helpers
# ---------------------------------------------------------------------------


def test_get_member_user_ids_returns_all_members(
    db, member_user, second_user, family_with_second_member
):
    from app.families import repository

    ids = repository.get_member_user_ids(db, family_with_second_member.id)
    assert set(ids) == {member_user.id, second_user.id}


def test_get_member_user_ids_empty_for_unknown_family(db):
    from app.families import repository

    assert repository.get_member_user_ids(db, 99999) == []


# ---------------------------------------------------------------------------
# Leave / remove cleanup matrix (NEU-340 §7)
# ---------------------------------------------------------------------------


def test_leave_cleans_claims_and_collection_items_both_ways(
    db, client, member_user, second_user, second_headers, family_with_second_member
):
    fam = family_with_second_member  # member_user (organizer) + second_user (member), no other tie
    gift_a, gift_b, item_a, item_b = _seed_cross_artifacts(db, member_user, second_user)

    resp = client.delete(
        f"/families/{fam.id}/members/{second_user.id}", headers=second_headers
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    assert not _is_claimed(db, gift_a)
    assert not _is_claimed(db, gift_b)
    assert not _item_exists(db, item_a.id)
    assert not _item_exists(db, item_b.id)


def test_organizer_removal_cleans_like_self_leave(
    db, client, member_user, member_headers, second_user, family_with_second_member
):
    fam = family_with_second_member
    gift_a, gift_b, item_a, item_b = _seed_cross_artifacts(db, member_user, second_user)

    resp = client.delete(
        f"/families/{fam.id}/members/{second_user.id}", headers=member_headers
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    assert not _is_claimed(db, gift_a)
    assert not _is_claimed(db, gift_b)
    assert not _item_exists(db, item_a.id)
    assert not _item_exists(db, item_b.id)


def test_leave_keeps_artifacts_when_connection_remains(
    db, client, member_user, second_user, second_headers, family_with_second_member
):
    fam = family_with_second_member
    _accept_connection(db, member_user, second_user)  # independent access path
    gift_a, gift_b, item_a, item_b = _seed_cross_artifacts(db, member_user, second_user)

    resp = client.delete(
        f"/families/{fam.id}/members/{second_user.id}", headers=second_headers
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    assert _is_claimed(db, gift_a)
    assert _is_claimed(db, gift_b)
    assert _item_exists(db, item_a.id)
    assert _item_exists(db, item_b.id)


def test_leave_keeps_artifacts_when_second_family_remains(
    db, client, member_user, second_user, second_headers, family_with_second_member
):
    fam = family_with_second_member
    # A second shared family between the same two users.
    fam2 = Family(name="Second Family", created_by_id=member_user.id)
    db.add(fam2)
    db.flush()
    db.add_all([
        FamilyMember(family_id=fam2.id, user_id=member_user.id, role="organizer"),
        FamilyMember(family_id=fam2.id, user_id=second_user.id, role="member"),
    ])
    db.flush()
    gift_a, gift_b, item_a, item_b = _seed_cross_artifacts(db, member_user, second_user)

    resp = client.delete(
        f"/families/{fam.id}/members/{second_user.id}", headers=second_headers
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    assert _is_claimed(db, gift_a)
    assert _is_claimed(db, gift_b)
    assert _item_exists(db, item_a.id)
    assert _item_exists(db, item_b.id)


def test_leave_does_not_touch_list_shares(
    db, client, member_user, second_user, second_headers, family_with_second_member
):
    fam = family_with_second_member
    shared = GiftList(name="Member's shared list", owner_id=member_user.id)
    db.add(shared)
    db.flush()
    share = ListShare(list_id=shared.id, user_id=second_user.id)
    db.add(share)
    db.flush()

    resp = client.delete(
        f"/families/{fam.id}/members/{second_user.id}", headers=second_headers
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    remaining = db.execute(
        select(ListShare).where(
            ListShare.list_id == shared.id, ListShare.user_id == second_user.id
        )
    ).scalar_one_or_none()
    assert remaining is not None  # cleanup must never delete shares


# ---------------------------------------------------------------------------
# Family-delete cleanup matrix (NEU-340 §7)
# ---------------------------------------------------------------------------


def test_delete_family_cleans_only_non_overlapping_pairs(
    db, client, member_user, member_headers, second_user, third_user, family
):
    # One family of three; member_user is organizer.
    db.add_all([
        FamilyMember(family_id=family.id, user_id=second_user.id, role="member"),
        FamilyMember(family_id=family.id, user_id=third_user.id, role="member"),
    ])
    db.flush()
    # member_user <-> third_user also have an accepted connection (access persists).
    _accept_connection(db, member_user, third_user)

    ms_a, ms_b, ms_item_a, ms_item_b = _seed_cross_artifacts(db, member_user, second_user)
    mt_a, mt_b, mt_item_a, mt_item_b = _seed_cross_artifacts(db, member_user, third_user)
    st_a, st_b, st_item_a, st_item_b = _seed_cross_artifacts(db, second_user, third_user)

    resp = client.delete(f"/families/{family.id}", headers=member_headers)
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    # member <-> second: no other tie -> cleaned
    assert not _is_claimed(db, ms_a) and not _is_claimed(db, ms_b)
    assert not _item_exists(db, ms_item_a.id) and not _item_exists(db, ms_item_b.id)

    # second <-> third: no other tie -> cleaned
    assert not _is_claimed(db, st_a) and not _is_claimed(db, st_b)
    assert not _item_exists(db, st_item_a.id) and not _item_exists(db, st_item_b.id)

    # member <-> third: connection remains -> untouched
    assert _is_claimed(db, mt_a) and _is_claimed(db, mt_b)
    assert _item_exists(db, mt_item_a.id) and _item_exists(db, mt_item_b.id)


def test_delete_family_unclaims_when_no_other_tie(
    db, client, member_user, member_headers, second_user, family_with_second_member
):
    fam = family_with_second_member
    gift_a, gift_b, item_a, item_b = _seed_cross_artifacts(db, member_user, second_user)

    resp = client.delete(f"/families/{fam.id}", headers=member_headers)
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    assert not _is_claimed(db, gift_a)
    assert not _is_claimed(db, gift_b)
    assert not _item_exists(db, item_a.id)
    assert not _item_exists(db, item_b.id)


# ---------------------------------------------------------------------------
# Edge-case coverage (NEU-355)
# ---------------------------------------------------------------------------


def test_three_family_chain_selective_cleanup_on_delete(
    db, client, member_user, member_headers, second_user, third_user
):
    """Scenario 1 — A&B share F1+F2; A&C share F2+F3.
    Deleting F1 must not clean A↔B (still co-members via F2). A↔C unaffected."""
    # Build F1 (A+B), F2 (A+B+C), F3 (A+C)
    f1 = Family(name="F1", created_by_id=member_user.id)
    f2 = Family(name="F2", created_by_id=member_user.id)
    f3 = Family(name="F3", created_by_id=member_user.id)
    db.add_all([f1, f2, f3])
    db.flush()

    db.add_all([
        FamilyMember(family_id=f1.id, user_id=member_user.id, role="organizer"),
        FamilyMember(family_id=f1.id, user_id=second_user.id, role="member"),
        FamilyMember(family_id=f2.id, user_id=member_user.id, role="organizer"),
        FamilyMember(family_id=f2.id, user_id=second_user.id, role="member"),
        FamilyMember(family_id=f2.id, user_id=third_user.id, role="member"),
        FamilyMember(family_id=f3.id, user_id=member_user.id, role="organizer"),
        FamilyMember(family_id=f3.id, user_id=third_user.id, role="member"),
    ])
    db.flush()

    gift_ab, gift_ba, item_ab, item_ba = _seed_cross_artifacts(db, member_user, second_user)
    gift_ac, gift_ca, item_ac, item_ca = _seed_cross_artifacts(db, member_user, third_user)

    resp = client.delete(f"/families/{f1.id}", headers=member_headers)
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    # A↔B: still co-members in F2 — no cleanup
    assert _is_claimed(db, gift_ab)
    assert _is_claimed(db, gift_ba)
    assert _item_exists(db, item_ab.id)
    assert _item_exists(db, item_ba.id)

    # A↔C: not in F1 at all — completely unaffected (still in F2+F3)
    assert _is_claimed(db, gift_ac)
    assert _is_claimed(db, gift_ca)
    assert _item_exists(db, item_ac.id)
    assert _item_exists(db, item_ca.id)


def test_four_member_family_delete_all_pairs_cleaned(
    db, client, member_user, member_headers, second_user, third_user
):
    """Scenario 2 — Family of 4 (A, B, C, D), no other ties.
    Deleting cleans all n·(n-1)/2 = 6 pairs."""
    fourth_user = User(email="fourth@test.com", name="Fourth", role="member", password_hash="x")
    fourth_user.set_password("fourth123")
    db.add(fourth_user)
    db.flush()

    fam = Family(name="Big Family", created_by_id=member_user.id)
    db.add(fam)
    db.flush()
    db.add_all([
        FamilyMember(family_id=fam.id, user_id=member_user.id, role="organizer"),
        FamilyMember(family_id=fam.id, user_id=second_user.id, role="member"),
        FamilyMember(family_id=fam.id, user_id=third_user.id, role="member"),
        FamilyMember(family_id=fam.id, user_id=fourth_user.id, role="member"),
    ])
    db.flush()

    users = [member_user, second_user, third_user, fourth_user]
    pairs = [(users[i], users[j]) for i in range(len(users)) for j in range(i + 1, len(users))]
    artifacts = [_seed_cross_artifacts(db, a, b) for a, b in pairs]

    resp = client.delete(f"/families/{fam.id}", headers=member_headers)
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    for gift_a, gift_b, item_a, item_b in artifacts:
        assert not _is_claimed(db, gift_a), f"gift {gift_a.id} still claimed after family delete"
        assert not _is_claimed(db, gift_b), f"gift {gift_b.id} still claimed after family delete"
        assert not _item_exists(db, item_a.id), f"item {item_a.id} still exists after family delete"
        assert not _item_exists(db, item_b.id), f"item {item_b.id} still exists after family delete"


def test_bidirectional_cleanup_depth_explicit(
    db, client, member_user, second_user, second_headers, family_with_second_member
):
    """Scenario 3 — Make the bidirectional cleanup explicit in 4 directions.
    Also verifies list_shares are untouched."""
    fam = family_with_second_member  # no other tie between member_user and second_user

    # Create a list_share that must survive the cleanup
    shared_list = GiftList(name="Shared List", owner_id=member_user.id)
    db.add(shared_list)
    db.flush()
    share = ListShare(list_id=shared_list.id, user_id=second_user.id)
    db.add(share)
    db.flush()

    gift_a, gift_b, item_a, item_b = _seed_cross_artifacts(db, member_user, second_user)
    # gift_a is on A's list, claimed by B; gift_b is on B's list, claimed by A
    # item_a is in A's collection pointing at B's list; item_b is in B's collection pointing at A's list

    resp = client.delete(
        f"/families/{fam.id}/members/{second_user.id}", headers=second_headers
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    # Direction 1: A's gift claimed by B → unclaimed
    assert not _is_claimed(db, gift_a), "A's gift should be unclaimed after B leaves"
    # Direction 2: B's gift claimed by A → unclaimed
    assert not _is_claimed(db, gift_b), "B's gift should be unclaimed after B leaves"
    # Direction 3: A's collection item → B's list → deleted
    assert not _item_exists(db, item_a.id), "A's collection item pointing to B's list should be deleted"
    # Direction 4: B's collection item → A's list → deleted
    assert not _item_exists(db, item_b.id), "B's collection item pointing to A's list should be deleted"

    # List share must be untouched
    remaining_share = db.execute(
        select(ListShare).where(
            ListShare.list_id == shared_list.id, ListShare.user_id == second_user.id
        )
    ).scalar_one_or_none()
    assert remaining_share is not None, "list_shares must never be deleted by family cleanup"


def test_third_party_not_affected_when_still_has_access(
    db, client, member_user, member_headers, second_user, third_user
):
    """Scenario 4 — User D (third_user) still shares a different family with A.
    After B leaves A's family, D's claim on A's gift and D's collection item → UNTOUCHED."""
    # F_ab: A+B share (no other tie between A and B)
    f_ab = Family(name="AB Family", created_by_id=member_user.id)
    db.add(f_ab)
    db.flush()
    db.add_all([
        FamilyMember(family_id=f_ab.id, user_id=member_user.id, role="organizer"),
        FamilyMember(family_id=f_ab.id, user_id=second_user.id, role="member"),
    ])
    db.flush()

    # F_ad: A+D share (D retains access to A's lists)
    f_ad = Family(name="AD Family", created_by_id=member_user.id)
    db.add(f_ad)
    db.flush()
    db.add_all([
        FamilyMember(family_id=f_ad.id, user_id=member_user.id, role="organizer"),
        FamilyMember(family_id=f_ad.id, user_id=third_user.id, role="member"),
    ])
    db.flush()

    # Seed cross-artifacts between A and B (will be cleaned)
    gift_ab, gift_ba, item_ab, item_ba = _seed_cross_artifacts(db, member_user, second_user)

    # D claims A's gift and has a collection item pointing at A's list
    list_a = GiftList(name="A's Extra List", owner_id=member_user.id)
    db.add(list_a)
    db.flush()
    gift_a_for_d = Gift(list_id=list_a.id, name="A gift for D to claim", claimed_by_id=third_user.id)
    db.add(gift_a_for_d)
    db.flush()
    coll_d = Collection(name="D's Collection", owner_id=third_user.id)
    db.add(coll_d)
    db.flush()
    item_d_on_a_list = CollectionItem(collection_id=coll_d.id, list_id=list_a.id)
    db.add(item_d_on_a_list)
    db.flush()

    # B leaves A's family
    resp = client.delete(
        f"/families/{f_ab.id}/members/{second_user.id}", headers=member_headers
    )
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    # A↔B artifacts: cleaned (no remaining shared access)
    assert not _is_claimed(db, gift_ab)
    assert not _is_claimed(db, gift_ba)
    assert not _item_exists(db, item_ab.id)
    assert not _item_exists(db, item_ba.id)

    # D's artifacts: UNTOUCHED (D still has access via F_ad)
    assert _is_claimed(db, gift_a_for_d), "D's claim on A's gift must not be removed"
    assert _item_exists(db, item_d_on_a_list.id), "D's collection item must not be removed"


def test_delete_family_overlap_with_connection_preserves_connected_pair(
    db, client, member_user, member_headers, second_user, third_user
):
    """Scenario 5 — Family with A, B, C; A&B also have an accepted connection.
    Delete the family → A↔B preserved, A↔C cleaned, B↔C cleaned."""
    fam = Family(name="Connection Family", created_by_id=member_user.id)
    db.add(fam)
    db.flush()
    db.add_all([
        FamilyMember(family_id=fam.id, user_id=member_user.id, role="organizer"),
        FamilyMember(family_id=fam.id, user_id=second_user.id, role="member"),
        FamilyMember(family_id=fam.id, user_id=third_user.id, role="member"),
    ])
    db.flush()

    # A↔B have an accepted connection (independent access path)
    _accept_connection(db, member_user, second_user)

    gift_ab, gift_ba, item_ab, item_ba = _seed_cross_artifacts(db, member_user, second_user)
    gift_ac, gift_ca, item_ac, item_ca = _seed_cross_artifacts(db, member_user, third_user)
    gift_bc, gift_cb, item_bc, item_cb = _seed_cross_artifacts(db, second_user, third_user)

    resp = client.delete(f"/families/{fam.id}", headers=member_headers)
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    # A↔B: connection remains → preserved
    assert _is_claimed(db, gift_ab), "gift_ab should still be claimed (A-B have a connection)"
    assert _is_claimed(db, gift_ba), "gift_ba should still be claimed (A-B have a connection)"
    assert _item_exists(db, item_ab.id), "item_ab should still exist (A-B have a connection)"
    assert _item_exists(db, item_ba.id), "item_ba should still exist (A-B have a connection)"

    # A↔C: no other tie → cleaned
    assert not _is_claimed(db, gift_ac), "gift_ac should be unclaimed (A-C: no other tie)"
    assert not _is_claimed(db, gift_ca), "gift_ca should be unclaimed (A-C: no other tie)"
    assert not _item_exists(db, item_ac.id), "item_ac should be deleted (A-C: no other tie)"
    assert not _item_exists(db, item_ca.id), "item_ca should be deleted (A-C: no other tie)"

    # B↔C: no other tie → cleaned
    assert not _is_claimed(db, gift_bc), "gift_bc should be unclaimed (B-C: no other tie)"
    assert not _is_claimed(db, gift_cb), "gift_cb should be unclaimed (B-C: no other tie)"
    assert not _item_exists(db, item_bc.id), "item_bc should be deleted (B-C: no other tie)"
    assert not _item_exists(db, item_cb.id), "item_cb should be deleted (B-C: no other tie)"


def test_empty_family_edges_succeed_without_error(
    db, client, member_user, member_headers, family
):
    """Scenario 6 — Organizer self-leaves as the sole remaining member.

    When the organizer is the *only* person left in a family they may self-leave
    (no other members would be left leaderless). The family persists in the
    database with 0 members. The creator can then delete that now-empty family
    even though they are no longer a member.
    """
    fam = family  # member_user is the sole organizer AND sole member

    # Action 1: organizer self-leaves as the sole remaining member → allowed (204)
    resp1 = client.delete(
        f"/families/{fam.id}/members/{member_user.id}", headers=member_headers
    )
    assert resp1.status_code == status.HTTP_204_NO_CONTENT

    # Family row must still exist with 0 members (verify via DB — no access path remains)
    from app.models.family import Family as FamilyModel
    family_row = db.get(FamilyModel, fam.id)
    assert family_row is not None, "Family should persist after the last member leaves"

    # Action 2: creator deletes the now-empty family (allowed without membership)
    resp2 = client.delete(f"/families/{fam.id}", headers=member_headers)
    assert resp2.status_code == status.HTTP_204_NO_CONTENT

    # Family should be gone
    gone = client.get(f"/families/{fam.id}", headers=member_headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


def test_last_organizer_guard_integration(
    db, client, member_user, member_headers, second_user, second_headers,
    family_with_second_organizer
):
    """Scenario 7 — Last-organizer guard at the router level.

    Part A: Create a fresh solo-organizer family; both remove and demote must return 409.
    Part B: family_with_second_organizer (two organizers) — demoting one succeeds and
            the remaining organizer retains the ability to perform organizer-only actions.
    """
    # Part A — single organizer with a plain member (the plain member is second_user).
    # The 409 guard fires because removing/demoting the sole organizer would leave
    # second_user in the family without any organizer.
    solo_fam = Family(name="Solo Family", created_by_id=member_user.id)
    db.add(solo_fam)
    db.flush()
    db.add_all([
        FamilyMember(family_id=solo_fam.id, user_id=member_user.id, role="organizer"),
        FamilyMember(family_id=solo_fam.id, user_id=second_user.id, role="member"),
    ])
    db.flush()

    # remove the last organizer while a plain member still exists → 409
    resp_remove = client.delete(
        f"/families/{solo_fam.id}/members/{member_user.id}", headers=member_headers
    )
    assert resp_remove.status_code == status.HTTP_409_CONFLICT

    # demote the last organizer while a plain member still exists → 409
    resp_demote = client.put(
        f"/families/{solo_fam.id}/members/{member_user.id}/role",
        json={"role": "member"},
        headers=member_headers,
    )
    assert resp_demote.status_code == status.HTTP_409_CONFLICT

    # Part B — two organizers: demote second_user → member should succeed
    fam2 = family_with_second_organizer
    resp_ok = client.put(
        f"/families/{fam2.id}/members/{second_user.id}/role",
        json={"role": "member"},
        headers=member_headers,
    )
    assert resp_ok.status_code == status.HTTP_200_OK
    roles = {m["user_id"]: m["role"] for m in resp_ok.json()["members"]}
    assert roles[member_user.id] == "organizer"
    assert roles[second_user.id] == "member"

    # The remaining organizer (member_user) still has control — can rename the family
    resp_rename = client.put(
        f"/families/{fam2.id}",
        json={"name": "Renamed After Demotion"},
        headers=member_headers,
    )
    assert resp_rename.status_code == status.HTTP_200_OK
    assert resp_rename.json()["name"] == "Renamed After Demotion"

    # The demoted user (now a plain member) can no longer rename the family
    resp_denied = client.put(
        f"/families/{fam2.id}",
        json={"name": "Should Be Denied"},
        headers=second_headers,
    )
    assert resp_denied.status_code == status.HTTP_403_FORBIDDEN
