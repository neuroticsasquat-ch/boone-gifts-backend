def test_create_invite_as_admin(client, admin_user, admin_headers):
    response = client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "invitee@test.com", "role": "member", "expires_in_days": 7},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "invitee@test.com"
    assert data["role"] == "member"
    assert data["token"] is not None
    assert data["used_at"] is None


def test_create_invite_as_member(client, member_user, member_headers):
    response = client.post(
        "/invites",
        headers=member_headers,
        json={"email": "nope@test.com"},
    )
    assert response.status_code == 403


def test_create_invite_default_role(client, admin_user, admin_headers):
    response = client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "default@test.com"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "member"


def test_list_invites_as_admin(client, admin_user, admin_headers):
    client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "list@test.com"},
    )
    response = client.get("/invites", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_list_invites_as_member(client, member_user, member_headers):
    response = client.get("/invites", headers=member_headers)
    assert response.status_code == 403


def test_delete_invite_as_admin(client, admin_user, admin_headers):
    create = client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "delete@test.com"},
    )
    invite_id = create.json()["id"]

    response = client.delete(f"/invites/{invite_id}", headers=admin_headers)
    assert response.status_code == 204


def test_delete_invite_as_member(client, admin_user, member_user, admin_headers, member_headers):
    create = client.post(
        "/invites",
        headers=admin_headers,
        json={"email": "nodelete@test.com"},
    )
    invite_id = create.json()["id"]

    response = client.delete(f"/invites/{invite_id}", headers=member_headers)
    assert response.status_code == 403
