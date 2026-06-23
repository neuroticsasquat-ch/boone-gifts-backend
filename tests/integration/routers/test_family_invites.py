from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.dependencies import create_access_token
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.family_member import FamilyMember
from app.models.user import User

SEND_EMAIL = "app.family_invites.service.send_email"


# ---------------------------------------------------------------------------
# Local fixtures — member_user (from conftest) is the family's organizer
# ---------------------------------------------------------------------------


@pytest.fixture
def family(db, member_user):
    fam = Family(name="Boone Family", created_by_id=member_user.id)
    db.add(fam)
    db.flush()
    db.add(FamilyMember(family_id=fam.id, user_id=member_user.id, role="organizer"))
    db.flush()
    return fam


@pytest.fixture
def plain_member(db):
    user = User(email="plainmember@test.com", name="Plain", role="member", password_hash="x")
    user.set_password("x")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def plain_member_headers(plain_member):
    return {"Authorization": f"Bearer {create_access_token(plain_member)}"}


@pytest.fixture
def family_with_plain_member(db, family, plain_member):
    db.add(FamilyMember(family_id=family.id, user_id=plain_member.id, role="member"))
    db.flush()
    return family


@pytest.fixture
def outsider(db):
    user = User(email="outsider@test.com", name="Outsider", role="member", password_hash="x")
    user.set_password("x")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def outsider_headers(outsider):
    return {"Authorization": f"Bearer {create_access_token(outsider)}"}


def _seed_invite(db, *, family_id, invited_by_id, email, token, accepted_at=None, expires_in_days=7):
    invite = FamilyInvite(
        family_id=family_id,
        email=email,
        role="member",
        simple_mode=False,
        token=token,
        invited_by_id=invited_by_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        accepted_at=accepted_at,
    )
    db.add(invite)
    db.flush()
    return invite


# ---------------------------------------------------------------------------
# POST /families/{id}/invites
# ---------------------------------------------------------------------------


def test_create_invite_new_email(client, member_headers, family):
    with patch(SEND_EMAIL) as mock_send:
        response = client.post(
            f"/families/{family.id}/invites",
            headers=member_headers,
            json={"email": "  NewPerson@Test.COM  "},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newperson@test.com"  # normalized
    assert data["role"] == "member"
    assert data["status"] == "pending"
    assert data["token"]
    mock_send.assert_called_once()
    assert "/register?family_invite=" in mock_send.call_args.kwargs["html"]


def test_create_invite_existing_user(client, member_headers, family, outsider):
    with patch(SEND_EMAIL) as mock_send:
        response = client.post(
            f"/families/{family.id}/invites",
            headers=member_headers,
            json={"email": outsider.email},
        )
    assert response.status_code == 201
    assert "/family-invites/" in mock_send.call_args.kwargs["html"]


def test_create_invite_role_organizer(client, member_headers, family):
    with patch(SEND_EMAIL):
        response = client.post(
            f"/families/{family.id}/invites",
            headers=member_headers,
            json={"email": "boss@test.com", "role": "organizer"},
        )
    assert response.status_code == 201
    assert response.json()["role"] == "organizer"


def test_create_invite_invalid_role(client, member_headers, family):
    response = client.post(
        f"/families/{family.id}/invites",
        headers=member_headers,
        json={"email": "x@test.com", "role": "admin"},
    )
    assert response.status_code == 422


def test_create_invite_already_member(client, member_headers, family_with_plain_member, plain_member):
    response = client.post(
        f"/families/{family_with_plain_member.id}/invites",
        headers=member_headers,
        json={"email": plain_member.email},
    )
    assert response.status_code == 409


def test_create_invite_duplicate_pending(client, member_headers, family):
    with patch(SEND_EMAIL):
        first = client.post(
            f"/families/{family.id}/invites",
            headers=member_headers,
            json={"email": "dupe@test.com"},
        )
        assert first.status_code == 201
        second = client.post(
            f"/families/{family.id}/invites",
            headers=member_headers,
            json={"email": "dupe@test.com"},
        )
    assert second.status_code == 409


def test_create_invite_non_organizer_forbidden(client, plain_member_headers, family_with_plain_member):
    response = client.post(
        f"/families/{family_with_plain_member.id}/invites",
        headers=plain_member_headers,
        json={"email": "x@test.com"},
    )
    assert response.status_code == 403


def test_create_invite_non_member_forbidden(client, outsider_headers, family):
    response = client.post(
        f"/families/{family.id}/invites",
        headers=outsider_headers,
        json={"email": "x@test.com"},
    )
    assert response.status_code == 403


def test_create_invite_family_not_found(client, member_headers):
    response = client.post(
        "/families/99999/invites",
        headers=member_headers,
        json={"email": "x@test.com"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /families/{id}/invites
# ---------------------------------------------------------------------------


def test_list_invites_pending_only(client, member_headers, family, member_user, db):
    _seed_invite(db, family_id=family.id, invited_by_id=member_user.id, email="pending@test.com", token="p1")
    _seed_invite(
        db, family_id=family.id, invited_by_id=member_user.id, email="gone@test.com", token="a1",
        accepted_at=datetime.now(timezone.utc),
    )
    _seed_invite(
        db, family_id=family.id, invited_by_id=member_user.id, email="old@test.com", token="e1",
        expires_in_days=-1,
    )

    response = client.get(f"/families/{family.id}/invites", headers=member_headers)
    assert response.status_code == 200
    rows = response.json()
    emails = {r["email"]: r["status"] for r in rows}
    assert "gone@test.com" not in emails  # accepted excluded
    assert emails["pending@test.com"] == "pending"
    assert emails["old@test.com"] == "expired"


def test_list_invites_non_organizer_forbidden(client, plain_member_headers, family_with_plain_member):
    response = client.get(
        f"/families/{family_with_plain_member.id}/invites", headers=plain_member_headers
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /families/{id}/invites/{invite_id}
# ---------------------------------------------------------------------------


def test_revoke_invite(client, member_headers, family, member_user, db):
    invite = _seed_invite(
        db, family_id=family.id, invited_by_id=member_user.id, email="revoke@test.com", token="r1"
    )
    response = client.delete(f"/families/{family.id}/invites/{invite.id}", headers=member_headers)
    assert response.status_code == 204

    remaining = client.get(f"/families/{family.id}/invites", headers=member_headers).json()
    assert all(r["id"] != invite.id for r in remaining)


def test_revoke_accepted_invite(client, member_headers, family, member_user, db):
    invite = _seed_invite(
        db, family_id=family.id, invited_by_id=member_user.id, email="acc@test.com", token="acc1",
        accepted_at=datetime.now(timezone.utc),
    )
    response = client.delete(f"/families/{family.id}/invites/{invite.id}", headers=member_headers)
    assert response.status_code == 409


def test_revoke_invite_not_found(client, member_headers, family):
    response = client.delete(f"/families/{family.id}/invites/99999", headers=member_headers)
    assert response.status_code == 404


def test_revoke_invite_non_organizer_forbidden(
    client, plain_member_headers, family_with_plain_member, member_user, db
):
    invite = _seed_invite(
        db, family_id=family_with_plain_member.id, invited_by_id=member_user.id,
        email="x@test.com", token="x1",
    )
    response = client.delete(
        f"/families/{family_with_plain_member.id}/invites/{invite.id}",
        headers=plain_member_headers,
    )
    assert response.status_code == 403


def test_list_invites_non_member_forbidden(client, outsider_headers, family):
    response = client.get(f"/families/{family.id}/invites", headers=outsider_headers)
    assert response.status_code == 403


def test_revoke_invite_non_member_forbidden(client, outsider_headers, family, member_user, db):
    invite = _seed_invite(
        db, family_id=family.id, invited_by_id=member_user.id,
        email="x2@test.com", token="x2",
    )
    response = client.delete(
        f"/families/{family.id}/invites/{invite.id}", headers=outsider_headers
    )
    assert response.status_code == 403
