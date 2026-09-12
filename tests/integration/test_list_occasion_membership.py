"""Occasion-share lifecycle across family membership changes (NEU-1265).

Joining a family shares nothing — members opt each list in themselves, and the
simple-mode auto-grant that used to do it for them is gone (ADR 0004). Leaving,
being removed, and family deletion all drop the affected shares, which is what
lets the read queries assume a share row implies live membership.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.dependencies import create_access_token
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.family_member import FamilyMember
from app.models.gift_list import GiftList
from app.models.list_occasion_share import ListOccasionShare
from app.models.occasion import Occasion
from app.models.user import User


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _mkuser(db, email, name):
    user = User(email=email, name=name, role="member", password_hash="x")
    user.set_password("pw123456")
    db.add(user)
    db.flush()
    return user


def _shared(db, list_id):
    return {
        row.occasion_id
        for row in db.query(ListOccasionShare).filter_by(list_id=list_id).all()
    }


def _mkoccasion(db, family, name, created_by):
    occasion = Occasion(
        family_id=family.id, name=name, created_by_id=created_by.id
    )
    db.add(occasion)
    db.flush()
    return occasion


@pytest.fixture
def invite_world(db):
    """Organizer with a family, and a pending invite for `joiner`."""
    organizer = _mkuser(db, "org@test.com", "Organizer")
    family = Family(name="The Boones", created_by_id=organizer.id)
    db.add(family)
    db.flush()
    db.add(FamilyMember(family_id=family.id, user_id=organizer.id, role="organizer"))
    db.flush()
    occasion = _mkoccasion(db, family, "Christmas 2026", organizer)

    def invite_for(user):
        invite = FamilyInvite(
            family_id=family.id,
            email=user.email,
            role="member",
            token=str(uuid4()),
            invited_by_id=organizer.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(invite)
        db.flush()
        return invite

    return SimpleNamespace(
        organizer=organizer, family=family, occasion=occasion, invite_for=invite_for
    )


def _mklist(db, owner, name, archived=False):
    gift_list = GiftList(name=name, owner_id=owner.id, is_archived=archived)
    db.add(gift_list)
    db.flush()
    return gift_list


# ---------------------------------------------------------------------------
# Gaining membership
# ---------------------------------------------------------------------------


def test_joiner_shares_nothing_until_they_opt_in(client, db, invite_world):
    joiner = _mkuser(db, "joiner@test.com", "Joiner")
    existing = _mklist(db, joiner, "Kept Private")
    invite = invite_world.invite_for(joiner)

    client.post(f"/families/invites/{invite.token}/accept", headers=_auth(joiner))
    assert _shared(db, existing.id) == set()

    shared = client.get(
        "/lists?filter=shared", headers=_auth(invite_world.organizer)
    ).json()
    assert "Kept Private" not in {l["name"] for l in shared}

    # Opting in afterwards works.
    client.put(
        f"/lists/{existing.id}/occasions/{invite_world.occasion.id}",
        headers=_auth(joiner),
    )
    assert _shared(db, existing.id) == {invite_world.occasion.id}


def test_family_creator_shares_nothing(client, db):
    creator = _mkuser(db, "creator@test.com", "Creator")
    existing = _mklist(db, creator, "Creator's List")

    client.post("/families", headers=_auth(creator), json={"name": "New Family"})
    assert _shared(db, existing.id) == set()


def test_register_via_family_invite_does_not_error(client, db, invite_world):
    """Registering through a family invite joins the family and shares nothing."""
    invite = FamilyInvite(
        family_id=invite_world.family.id,
        email="newbie@test.com",
        role="member",
        token=str(uuid4()),
        invited_by_id=invite_world.organizer.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    db.flush()

    resp = client.post(
        "/auth/register",
        json={"token": invite.token, "name": "Newbie", "password": "pw123456"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Losing membership
# ---------------------------------------------------------------------------


@pytest.fixture
def shared_world(db):
    """Owner and organizer in a family; owner's list shared to its occasion."""
    organizer = _mkuser(db, "org@test.com", "Organizer")
    owner = _mkuser(db, "owner@test.com", "Owner")
    family = Family(name="The Boones", created_by_id=organizer.id)
    db.add(family)
    db.flush()
    db.add_all(
        [
            FamilyMember(family_id=family.id, user_id=organizer.id, role="organizer"),
            FamilyMember(family_id=family.id, user_id=owner.id, role="member"),
        ]
    )
    db.flush()
    occasion = _mkoccasion(db, family, "Christmas 2026", organizer)
    gift_list = _mklist(db, owner, "Owner's List")
    db.add(ListOccasionShare(list_id=gift_list.id, occasion_id=occasion.id))
    db.flush()
    return SimpleNamespace(
        organizer=organizer,
        owner=owner,
        family=family,
        occasion=occasion,
        gift_list=gift_list,
    )


def test_leaving_a_family_deletes_the_departing_members_shares(
    client, db, shared_world
):
    w = shared_world
    resp = client.delete(
        f"/families/{w.family.id}/members/{w.owner.id}", headers=_auth(w.owner)
    )
    assert resp.status_code == 204
    assert _shared(db, w.gift_list.id) == set()

    visible = client.get("/lists?filter=shared", headers=_auth(w.organizer)).json()
    assert "Owner's List" not in {l["name"] for l in visible}


def test_being_removed_deletes_the_departing_members_shares(client, db, shared_world):
    w = shared_world
    resp = client.delete(
        f"/families/{w.family.id}/members/{w.owner.id}", headers=_auth(w.organizer)
    )
    assert resp.status_code == 204
    assert _shared(db, w.gift_list.id) == set()


def test_removal_leaves_a_co_members_shares_alone(client, db, shared_world):
    w = shared_world
    organizer_list = _mklist(db, w.organizer, "Organizer's List")
    db.add(ListOccasionShare(list_id=organizer_list.id, occasion_id=w.occasion.id))
    db.flush()

    client.delete(
        f"/families/{w.family.id}/members/{w.owner.id}", headers=_auth(w.organizer)
    )
    assert _shared(db, organizer_list.id) == {w.occasion.id}


def test_deleting_a_family_deletes_all_of_its_shares(client, db, shared_world):
    w = shared_world
    resp = client.delete(f"/families/{w.family.id}", headers=_auth(w.organizer))
    assert resp.status_code == 204
    assert _shared(db, w.gift_list.id) == set()


def test_leaving_one_family_leaves_shares_on_another_intact(client, db, shared_world):
    w = shared_world
    other = Family(name="The Smiths", created_by_id=w.owner.id)
    db.add(other)
    db.flush()
    db.add(FamilyMember(family_id=other.id, user_id=w.owner.id, role="organizer"))
    other_occasion = _mkoccasion(db, other, "Christmas 2026", w.owner)
    db.add(ListOccasionShare(list_id=w.gift_list.id, occasion_id=other_occasion.id))
    db.flush()

    client.delete(
        f"/families/{w.family.id}/members/{w.owner.id}", headers=_auth(w.owner)
    )
    assert _shared(db, w.gift_list.id) == {other_occasion.id}


def test_leaving_deletes_shares_on_every_occasion_of_that_family(
    client, db, shared_world
):
    """A family may run several occasions at once; a departure has to clear the
    departing member's shares on all of them, not just the one it found first."""
    w = shared_world
    sibling = _mkoccasion(db, w.family, "Gran's 80th", w.organizer)
    db.add(ListOccasionShare(list_id=w.gift_list.id, occasion_id=sibling.id))
    db.flush()

    client.delete(
        f"/families/{w.family.id}/members/{w.owner.id}", headers=_auth(w.owner)
    )
    assert _shared(db, w.gift_list.id) == set()
