from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.family_member import FamilyMember
from app.models.invite import Invite
from app.models.user import User


COOKIE_NAME = "boone_refresh_token"


def _seed_family_invite(
    db,
    *,
    inviter,
    email,
    token,
    role="member",
    accepted_at=None,
    declined_at=None,
    expires_in_days=7,
    family_name="Boone Family",
):
    family = Family(name=family_name, created_by_id=inviter.id)
    db.add(family)
    db.flush()
    db.add(FamilyMember(family_id=family.id, user_id=inviter.id, role="organizer"))
    invite = FamilyInvite(
        family_id=family.id,
        email=email,
        role=role,
        simple_mode=False,
        token=token,
        invited_by_id=inviter.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        accepted_at=accepted_at,
        declined_at=declined_at,
    )
    db.add(invite)
    db.flush()
    return family, invite


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

    client.cookies.set(COOKIE_NAME, refresh_cookie)
    response = client.post("/auth/refresh")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data
    # Cookie should be rotated
    assert COOKIE_NAME in response.cookies


def test_refresh_with_access_token_fails(client, admin_token):
    client.cookies.set(COOKIE_NAME, admin_token)
    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_refresh_with_invalid_token(client):
    client.cookies.set(COOKIE_NAME, "garbage")
    response = client.post("/auth/refresh")
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


def test_update_profile_returns_new_token(client, member_user, member_headers):
    response = client.put(
        "/auth/profile",
        json={"name": "Updated Name"},
        headers=member_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data
    assert data["token_type"] == "bearer"
    assert COOKIE_NAME in response.cookies


def test_update_profile_token_contains_updated_name(client, member_user, member_headers):
    response = client.put(
        "/auth/profile",
        json={"name": "New Display Name"},
        headers=member_headers,
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_iat": False},
    )
    assert payload["name"] == "New Display Name"


def test_update_profile_persists_name_in_db(client, member_user, member_headers, db):
    response = client.put(
        "/auth/profile",
        json={"name": "Persisted Name"},
        headers=member_headers,
    )
    assert response.status_code == 200
    db.refresh(member_user)
    assert member_user.name == "Persisted Name"


def test_update_profile_requires_auth(client):
    response = client.put("/auth/profile", json={"name": "Anonymous"})
    assert response.status_code == 401


# --- invite-info: family tokens ---


def test_invite_info_family_token(client, member_user, db):
    _seed_family_invite(db, inviter=member_user, email="newmember@test.com", token="fam-info-1")

    response = client.get("/auth/invite-info", params={"token": "fam-info-1"})
    assert response.status_code == 200
    assert response.json() == {"email": "newmember@test.com", "family_name": "Boone Family"}


def test_invite_info_admin_token_has_null_family_name(client, admin_user, db):
    invite = Invite(
        email="admin-invitee@test.com",
        role="member",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=admin_user.id,
    )
    db.add(invite)
    db.flush()

    response = client.get("/auth/invite-info", params={"token": invite.token})
    assert response.status_code == 200
    assert response.json() == {"email": "admin-invitee@test.com", "family_name": None}


def test_invite_info_expired_family_token(client, member_user, db):
    _seed_family_invite(
        db, inviter=member_user, email="x@test.com", token="fam-info-exp", expires_in_days=-1
    )
    response = client.get("/auth/invite-info", params={"token": "fam-info-exp"})
    assert response.status_code == 400


def test_invite_info_accepted_family_token(client, member_user, db):
    _seed_family_invite(
        db,
        inviter=member_user,
        email="x@test.com",
        token="fam-info-acc",
        accepted_at=datetime.now(timezone.utc),
    )
    response = client.get("/auth/invite-info", params={"token": "fam-info-acc"})
    assert response.status_code == 400


# --- register via family invite ---


def test_register_family_invite_creates_member(client, member_user, db):
    family, invite = _seed_family_invite(
        db, inviter=member_user, email="newmember@test.com", token="fam-reg-1", role="organizer"
    )

    response = client.post(
        "/auth/register",
        json={"token": "fam-reg-1", "name": "New Member", "password": "newpass123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert COOKIE_NAME in response.cookies

    new_user = db.query(User).filter_by(email="newmember@test.com").one()
    assert new_user.role == "member"  # app role — NOT the family "organizer" role

    membership = db.query(FamilyMember).filter_by(
        family_id=family.id, user_id=new_user.id
    ).one()
    assert membership.role == "organizer"  # family role from the invite

    db.refresh(invite)
    assert invite.accepted_at is not None


def test_register_family_invite_token_joins_family_end_to_end(client, member_user, db):
    family, _ = _seed_family_invite(
        db, inviter=member_user, email="newmember2@test.com", token="fam-reg-2", role="member"
    )

    token = client.post(
        "/auth/register",
        json={"token": "fam-reg-2", "name": "New Member", "password": "newpass123"},
    ).json()["access_token"]

    # The freshly-issued token authenticates and the user is in the family.
    families = client.get("/families", headers={"Authorization": f"Bearer {token}"})
    assert families.status_code == 200
    joined = [f for f in families.json() if f["id"] == family.id]
    assert len(joined) == 1
    assert joined[0]["role"] == "member"


def test_register_family_invite_existing_account_rejected(client, member_user, db):
    # member_user already exists; invite is addressed to their email.
    _seed_family_invite(
        db, inviter=member_user, email=member_user.email, token="fam-reg-dup"
    )
    response = client.post(
        "/auth/register",
        json={"token": "fam-reg-dup", "name": "Dup", "password": "newpass123"},
    )
    assert response.status_code == 400


def test_register_expired_family_invite(client, member_user, db):
    _seed_family_invite(
        db, inviter=member_user, email="late@test.com", token="fam-reg-exp", expires_in_days=-1
    )
    response = client.post(
        "/auth/register",
        json={"token": "fam-reg-exp", "name": "Late", "password": "newpass123"},
    )
    assert response.status_code == 400


def test_register_accepted_family_invite(client, member_user, db):
    _seed_family_invite(
        db,
        inviter=member_user,
        email="done@test.com",
        token="fam-reg-acc",
        accepted_at=datetime.now(timezone.utc),
    )
    response = client.post(
        "/auth/register",
        json={"token": "fam-reg-acc", "name": "Done", "password": "newpass123"},
    )
    assert response.status_code == 400


# --- simple_mode in PUT /auth/profile ---


def test_update_profile_sets_simple_mode_in_token(client, member_user, member_headers, db):
    response = client.put(
        "/auth/profile",
        json={"name": member_user.name, "simple_mode": True},
        headers=member_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    payload = jwt.decode(
        data["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_iat": False},
    )
    assert payload["simple_mode"] is True
    db.refresh(member_user)
    assert member_user.simple_mode is True


def test_update_profile_name_only_preserves_simple_mode(client, member_user, member_headers, db):
    member_user.simple_mode = True
    db.flush()

    response = client.put(
        "/auth/profile",
        json={"name": "new name"},
        headers=member_headers,
    )
    assert response.status_code == 200
    payload = jwt.decode(
        response.json()["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_iat": False},
    )
    assert payload["simple_mode"] is True
    db.refresh(member_user)
    assert member_user.simple_mode is True


def test_update_profile_clears_simple_mode_when_explicitly_false(
    client, member_user, member_headers, db
):
    member_user.simple_mode = True
    db.flush()

    response = client.put(
        "/auth/profile",
        json={"name": member_user.name, "simple_mode": False},
        headers=member_headers,
    )
    assert response.status_code == 200
    payload = jwt.decode(
        response.json()["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_iat": False},
    )
    assert payload["simple_mode"] is False
    db.refresh(member_user)
    assert member_user.simple_mode is False
