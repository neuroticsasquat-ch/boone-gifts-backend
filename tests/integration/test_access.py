from types import SimpleNamespace

import pytest

from app.dependencies import create_access_token
from app.models.connection import Connection
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_family_share import ListFamilyShare
from app.models.list_share import ListShare
from app.models.user import User


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.fixture
def matrix(db):
    """Owner A with a one-gift list, plus five users in distinct relationships:
    B = co-member of a family A granted the list to, C = connection only,
    D = direct share, E = stranger, F = co-member of a family A did NOT grant
    the list to."""

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
    f = mkuser("f@test.com", "Ungranted F")

    gift_list = GiftList(name="A's Wishlist", owner_id=a.id)
    db.add(gift_list)
    db.flush()
    gift = Gift(list_id=gift_list.id, name="A Book")
    db.add(gift)
    db.flush()

    # B shares a family with A, and A granted the list to it.
    family = Family(name="A & B Family", created_by_id=a.id)
    # F shares a different family with A, which A never granted the list to.
    ungranted = Family(name="A & F Family", created_by_id=a.id)
    db.add_all([family, ungranted])
    db.flush()
    db.add(FamilyMember(family_id=family.id, user_id=a.id, role="organizer"))
    db.add(FamilyMember(family_id=family.id, user_id=b.id, role="member"))
    db.add(FamilyMember(family_id=ungranted.id, user_id=a.id, role="organizer"))
    db.add(FamilyMember(family_id=ungranted.id, user_id=f.id, role="member"))
    db.add(ListFamilyShare(list_id=gift_list.id, family_id=family.id))

    # C has an accepted connection with A but no share.
    db.add(Connection(requester_id=a.id, addressee_id=c.id, status="accepted"))

    # D has a direct ListShare on A's list.
    db.add(ListShare(list_id=gift_list.id, user_id=d.id))
    db.flush()

    return SimpleNamespace(
        list_id=gift_list.id,
        gift_id=gift.id,
        a=a, b=b, c=c, d=d, e=e, f=f,
        family=family,
        ungranted=ungranted,
    )


def test_get_list_access_matrix(client, matrix):
    def status_for(user):
        return client.get(
            f"/lists/{matrix.list_id}", headers=_headers(user)
        ).status_code

    assert status_for(matrix.a) == 200  # owner
    assert status_for(matrix.b) == 200  # co-member of a granted family
    assert status_for(matrix.d) == 200  # direct share
    assert status_for(matrix.c) == 403  # connection only — no share, no grant
    assert status_for(matrix.e) == 403  # stranger
    assert status_for(matrix.f) == 403  # co-member, but the family has no grant


def test_family_member_can_claim(client, matrix):
    resp = client.post(
        f"/lists/{matrix.list_id}/gifts/{matrix.gift_id}/claim",
        headers=_headers(matrix.b),
    )
    assert resp.status_code == 200
    assert resp.json()["claimed_by_id"] == matrix.b.id


def test_ungranted_family_member_cannot_claim(client, matrix):
    resp = client.post(
        f"/lists/{matrix.list_id}/gifts/{matrix.gift_id}/claim",
        headers=_headers(matrix.f),
    )
    assert resp.status_code == 403


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


def test_users_share_access_unchanged_by_grants(db, matrix):
    """Criterion 21: two people in a family still share access for claim and
    collection cleanup even when no list is shared between them. `can_view_list`
    moved onto grants; `users_share_access` deliberately did not."""
    from app.access import can_view_list, users_share_access

    assert users_share_access(db, matrix.a.id, matrix.f.id) is True
    assert can_view_list(db, matrix.f, db.get(GiftList, matrix.list_id)) is False
