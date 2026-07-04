from types import SimpleNamespace

import pytest

from app.dependencies import create_access_token
from app.models.connection import Connection
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.models.user import User


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.fixture
def matrix(db):
    """Owner A with a one-gift list, plus four users in distinct relationships:
    B = family co-member, C = connection only, D = direct share, E = stranger."""

    def mkuser(email, name):
        u = User(email=email, name=name, role="member", password_hash="x")
        u.set_password("pw123456")
        db.add(u)
        db.flush()
        return u

    a = mkuser("a@test.com", "Owner A")
    b = mkuser("b@test.com", "Family B")
    c = mkuser("c@test.com", "Connection C")
    d = mkuser("d@test.com", "Share D")
    e = mkuser("e@test.com", "Stranger E")

    gift_list = GiftList(name="A's Wishlist", owner_id=a.id)
    db.add(gift_list)
    db.flush()
    gift = Gift(list_id=gift_list.id, name="A Book")
    db.add(gift)
    db.flush()

    # B shares a family with A.
    family = Family(name="A & B Family", created_by_id=a.id)
    db.add(family)
    db.flush()
    db.add(FamilyMember(family_id=family.id, user_id=a.id, role="organizer"))
    db.add(FamilyMember(family_id=family.id, user_id=b.id, role="member"))

    # C has an accepted connection with A but no share.
    db.add(Connection(requester_id=a.id, addressee_id=c.id, status="accepted"))

    # D has a direct ListShare on A's list.
    db.add(ListShare(list_id=gift_list.id, user_id=d.id))
    db.flush()

    return SimpleNamespace(
        list_id=gift_list.id, gift_id=gift.id, a=a, b=b, c=c, d=d, e=e
    )


def test_get_list_access_matrix(client, matrix):
    def status_for(user):
        return client.get(
            f"/lists/{matrix.list_id}", headers=_headers(user)
        ).status_code

    assert status_for(matrix.a) == 200  # owner
    assert status_for(matrix.b) == 200  # family co-member
    assert status_for(matrix.d) == 200  # direct share
    assert status_for(matrix.c) == 403  # connection only — no share, no family
    assert status_for(matrix.e) == 403  # stranger


def test_family_member_can_claim(client, matrix):
    resp = client.post(
        f"/lists/{matrix.list_id}/gifts/{matrix.gift_id}/claim",
        headers=_headers(matrix.b),
    )
    assert resp.status_code == 200
    assert resp.json()["claimed_by_id"] == matrix.b.id


def test_connection_only_cannot_claim(client, matrix):
    resp = client.post(
        f"/lists/{matrix.list_id}/gifts/{matrix.gift_id}/claim",
        headers=_headers(matrix.c),
    )
    assert resp.status_code == 403


def test_owner_sees_no_claim_info_after_family_claim(client, matrix):
    client.post(
        f"/lists/{matrix.list_id}/gifts/{matrix.gift_id}/claim",
        headers=_headers(matrix.b),
    )
    resp = client.get(f"/lists/{matrix.list_id}", headers=_headers(matrix.a))
    assert resp.status_code == 200
    gift = resp.json()["gifts"][0]
    assert "claimed_by_id" not in gift  # GiftOwnerRead omits claim fields
