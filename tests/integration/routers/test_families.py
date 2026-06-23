import pytest
from fastapi import status

from app.dependencies import create_access_token
from app.models.family import Family
from app.models.family_member import FamilyMember
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
    from app.models.gift_list import GiftList
    from app.models.gift import Gift
    from app.models.collection import Collection
    from app.models.collection_item import CollectionItem

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
    from sqlalchemy import select
    from app.models.gift import Gift

    row = db.execute(
        select(Gift.claimed_by_id).where(Gift.id == gift.id)
    ).scalar_one_or_none()
    return row is not None


def _item_exists(db, item_id):
    from sqlalchemy import select
    from app.models.collection_item import CollectionItem

    return db.execute(
        select(CollectionItem).where(CollectionItem.id == item_id)
    ).scalar_one_or_none() is not None


def _accept_connection(db, user_a, user_b):
    from app.models.connection import Connection

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


def test_remove_member_409_last_organizer(client, member_headers, member_user, family):
    response = client.delete(
        f"/families/{family.id}/members/{member_user.id}", headers=member_headers
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
    from sqlalchemy import select
    from app.models.gift_list import GiftList
    from app.models.list_share import ListShare

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
