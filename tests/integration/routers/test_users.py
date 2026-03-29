def test_list_users_as_admin(client, admin_user, admin_headers):
    response = client.get("/users", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["email"] == "admin@test.com"


def test_list_users_as_member(client, member_user, member_headers):
    response = client.get("/users", headers=member_headers)
    assert response.status_code == 403


def test_list_users_unauthenticated(client):
    response = client.get("/users")
    assert response.status_code == 401


def test_get_user_as_admin(client, admin_user, admin_headers):
    response = client.get(f"/users/{admin_user.id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "admin@test.com"


def test_get_user_includes_lists(client, admin_headers, member_user, sample_list):
    response = client.get(f"/users/{member_user.id}", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["lists"]) == 1
    assert data["lists"][0]["name"] == "Member's Wishlist"
    assert "gifts" not in data["lists"][0]


def test_get_user_not_found(client, admin_user, admin_headers):
    response = client.get("/users/99999", headers=admin_headers)
    assert response.status_code == 404


def test_update_user_as_admin(client, member_user, admin_headers):
    response = client.put(
        f"/users/{member_user.id}",
        headers=admin_headers,
        json={"name": "Updated Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


def test_update_user_as_member(client, admin_user, member_headers):
    response = client.put(
        f"/users/{admin_user.id}",
        headers=member_headers,
        json={"name": "Hacked"},
    )
    assert response.status_code == 403


def test_delete_user_as_admin(client, member_user, admin_headers):
    response = client.delete(
        f"/users/{member_user.id}", headers=admin_headers
    )
    assert response.status_code == 204


def test_delete_user_as_member(client, admin_user, member_headers):
    response = client.delete(
        f"/users/{admin_user.id}", headers=member_headers
    )
    assert response.status_code == 403
