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
