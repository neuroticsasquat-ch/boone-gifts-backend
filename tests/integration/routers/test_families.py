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
