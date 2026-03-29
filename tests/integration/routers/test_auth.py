from datetime import datetime, timedelta, timezone

from app.models.invite import Invite


COOKIE_NAME = "boone_refresh_token"


def test_login_success(client, admin_user):
    response = client.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data
    assert data["token_type"] == "bearer"
    assert COOKIE_NAME in response.cookies


def test_login_wrong_password(client, admin_user):
    response = client.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "wrong",
    })
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    response = client.post("/auth/login", json={
        "email": "nobody@test.com",
        "password": "whatever",
    })
    assert response.status_code == 401


def test_login_inactive_user(client, admin_user, db):
    admin_user.is_active = False
    db.flush()
    response = client.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123",
    })
    assert response.status_code == 401


def test_register_with_valid_invite(client, admin_user, db):
    invite = Invite(
        email="new@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin_user.id,
    )
    db.add(invite)
    db.flush()

    response = client.post("/auth/register", json={
        "token": invite.token,
        "name": "New User",
        "password": "newpass123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data
    assert COOKIE_NAME in response.cookies


def test_register_with_expired_invite(client, admin_user, db):
    invite = Invite(
        email="expired@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        invited_by_id=admin_user.id,
    )
    db.add(invite)
    db.flush()

    response = client.post("/auth/register", json={
        "token": invite.token,
        "name": "Expired",
        "password": "pass123",
    })
    assert response.status_code == 400


def test_register_with_used_invite(client, admin_user, db):
    invite = Invite(
        email="used@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin_user.id,
    )
    invite.used_at = datetime.now(timezone.utc)
    db.add(invite)
    db.flush()

    response = client.post("/auth/register", json={
        "token": invite.token,
        "name": "Used",
        "password": "pass123",
    })
    assert response.status_code == 400


def test_register_with_invalid_token(client):
    response = client.post("/auth/register", json={
        "token": "nonexistent-token",
        "name": "Bad",
        "password": "pass123",
    })
    assert response.status_code == 400


def test_refresh_token(client, admin_user):
    login = client.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123",
    })
    refresh_cookie = login.cookies[COOKIE_NAME]

    response = client.post("/auth/refresh", cookies={COOKIE_NAME: refresh_cookie})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data
    # Cookie should be rotated
    assert COOKIE_NAME in response.cookies


def test_refresh_with_access_token_fails(client, admin_token):
    response = client.post("/auth/refresh", cookies={COOKIE_NAME: admin_token})
    assert response.status_code == 401


def test_refresh_with_invalid_token(client):
    response = client.post("/auth/refresh", cookies={COOKIE_NAME: "garbage"})
    assert response.status_code == 401


def test_refresh_without_cookie(client):
    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_logout_clears_cookie(client, admin_user):
    login = client.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123",
    })
    assert COOKIE_NAME in login.cookies

    response = client.post("/auth/logout")
    assert response.status_code == 204
    # Cookie should be set with max-age=0 to delete it
    set_cookie = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert 'Max-Age=0' in set_cookie


def test_logout_without_cookie(client):
    response = client.post("/auth/logout")
    assert response.status_code == 204
