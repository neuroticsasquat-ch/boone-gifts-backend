def test_change_password_requires_authentication(client):
    response = client.post(
        "/auth/change-password",
        json={"current_password": "x", "new_password": "y"},
    )
    assert response.status_code in (401, 403)


def test_change_password_rejects_wrong_current_password(client, member_user, member_headers):
    response = client.post(
        "/auth/change-password",
        headers=member_headers,
        json={"current_password": "wrong", "new_password": "new-password-123"},
    )
    assert response.status_code == 400


def test_change_password_returns_new_access_token(client, member_user, member_headers):
    response = client.post(
        "/auth/change-password",
        headers=member_headers,
        json={"current_password": "member123", "new_password": "new-password-123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["access_token"]


def test_change_password_sets_refresh_cookie(client, member_user, member_headers):
    response = client.post(
        "/auth/change-password",
        headers=member_headers,
        json={"current_password": "member123", "new_password": "new-password-123"},
    )
    assert "boone_refresh_token" in response.cookies


def test_change_password_lets_user_log_in_with_new_password(
    client, member_user, member_headers
):
    client.post(
        "/auth/change-password",
        headers=member_headers,
        json={"current_password": "member123", "new_password": "new-password-123"},
    )

    login = client.post(
        "/auth/login",
        json={"email": "member@test.com", "password": "new-password-123"},
    )
    assert login.status_code == 200


def test_change_password_rejects_old_password_on_login(
    client, member_user, member_headers
):
    client.post(
        "/auth/change-password",
        headers=member_headers,
        json={"current_password": "member123", "new_password": "new-password-123"},
    )

    login = client.post(
        "/auth/login",
        json={"email": "member@test.com", "password": "member123"},
    )
    assert login.status_code == 401


def test_change_password_invalidates_old_refresh_tokens(
    client, member_user, member_headers
):
    login = client.post(
        "/auth/login",
        json={"email": "member@test.com", "password": "member123"},
    )
    client.cookies.set("boone_refresh_token", login.cookies["boone_refresh_token"])

    change = client.post(
        "/auth/change-password",
        headers=member_headers,
        json={"current_password": "member123", "new_password": "new-password-123"},
    )
    assert change.status_code == 200

    client.cookies.set("boone_refresh_token", login.cookies["boone_refresh_token"])
    refresh = client.post("/auth/refresh")
    assert refresh.status_code == 401


def test_returned_access_token_works_immediately(
    client, member_user, member_headers
):
    response = client.post(
        "/auth/change-password",
        headers=member_headers,
        json={"current_password": "member123", "new_password": "new-password-123"},
    )
    assert response.status_code == 200
    new_token = response.json()["access_token"]

    me_response = client.get(
        "/lists", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert me_response.status_code == 200
