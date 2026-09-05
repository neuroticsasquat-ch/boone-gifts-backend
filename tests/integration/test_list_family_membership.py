"""Grant lifecycle across family membership changes (NEU-1202 §2.5).

Simple-mode members have their existing lists auto-granted when they join,
because the toggles are forbidden to them. Full-mode members opt in themselves.
Leaving, being removed, and family deletion all drop the affected grants.
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
from app.models.list_family_share import ListFamilyShare
from app.models.user import User


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _mkuser(db, email, name, simple_mode=False):
    user = User(
        email=email, name=name, role="member", password_hash="x", simple_mode=simple_mode
    )
    user.set_password("pw123456")
    db.add(user)
    db.flush()
    return user


def _granted(db, list_id):
    return {
        row.family_id
        for row in db.query(ListFamilyShare).filter_by(list_id=list_id).all()
    }


@pytest.fixture
def invite_world(db):
    """Organizer with a family, and a pending invite for `joiner`."""
    organizer = _mkuser(db, "org@test.com", "Organizer")
    family = Family(name="The Boones", created_by_id=organizer.id)
    db.add(family)
    db.flush()
    db.add(FamilyMember(family_id=family.id, user_id=organizer.id, role="organizer"))
    db.flush()

    def invite_for(user):
        invite = FamilyInvite(
            family_id=family.id,
            email=user.email,
            role="member",
            simple_mode=user.simple_mode,
            token=str(uuid4()),
            invited_by_id=organizer.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(invite)
        db.flush()
        return invite

    return SimpleNamespace(organizer=organizer, family=family, invite_for=invite_for)


def _mklist(db, owner, name, archived=False):
    gift_list = GiftList(name=name, owner_id=owner.id, is_archived=archived)
    db.add(gift_list)
    db.flush()
    return gift_list


# ---------------------------------------------------------------------------
# Gaining membership
# ---------------------------------------------------------------------------


def test_simple_mode_joiner_gets_existing_lists_granted(client, db, invite_world):
    joiner = _mkuser(db, "simple@test.com", "Simple", simple_mode=True)
    existing = _mklist(db, joiner, "Joiner's List")
    invite = invite_world.invite_for(joiner)

    resp = client.post(
        f"/families/invites/{invite.token}/accept", headers=_auth(joiner)
    )
    assert resp.status_code == 200
    assert _granted(db, existing.id) == {invite_world.family.id}

    # And the organizer now sees it in the family view.
    fam = client.get(
        "/lists?filter=family", headers=_auth(invite_world.organizer)
    ).json()
    assert "Joiner's List" in {l["name"] for l in fam}


def test_simple_mode_auto_grant_skips_archived_lists(client, db, invite_world):
    joiner = _mkuser(db, "simple@test.com", "Simple", simple_mode=True)
    archived = _mklist(db, joiner, "Old List", archived=True)
    invite = invite_world.invite_for(joiner)

    client.post(f"/families/invites/{invite.token}/accept", headers=_auth(joiner))
    assert _granted(db, archived.id) == set()


def test_full_mode_joiner_shares_nothing_until_they_opt_in(client, db, invite_world):
    joiner = _mkuser(db, "full@test.com", "Full", simple_mode=False)
    existing = _mklist(db, joiner, "Kept Private")
    invite = invite_world.invite_for(joiner)

    client.post(f"/families/invites/{invite.token}/accept", headers=_auth(joiner))
    assert _granted(db, existing.id) == set()

    fam = client.get(
        "/lists?filter=family", headers=_auth(invite_world.organizer)
    ).json()
    assert "Kept Private" not in {l["name"] for l in fam}

    # Opting in afterwards works.
    client.put(
        f"/lists/{existing.id}/families/{invite_world.family.id}",
        headers=_auth(joiner),
    )
    assert _granted(db, existing.id) == {invite_world.family.id}


def test_simple_mode_family_creator_gets_existing_lists_granted(client, db):
    creator = _mkuser(db, "simple@test.com", "Simple", simple_mode=True)
    existing = _mklist(db, creator, "Creator's List")

    resp = client.post(
        "/families", headers=_auth(creator), json={"name": "New Family"}
    )
    assert resp.status_code == 201
    assert _granted(db, existing.id) == {resp.json()["id"]}


def test_full_mode_family_creator_grants_nothing(client, db):
    creator = _mkuser(db, "full@test.com", "Full")
    existing = _mklist(db, creator, "Creator's List")

    client.post("/families", headers=_auth(creator), json={"name": "New Family"})
    assert _granted(db, existing.id) == set()


def test_register_via_family_invite_does_not_error(client, db, invite_world):
    """The new account owns no lists, so the auto-grant is a no-op — but the
    hook still runs on this path and must not break registration."""
    invite = FamilyInvite(
        family_id=invite_world.family.id,
        email="newbie@test.com",
        role="member",
        simple_mode=True,
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
def granted_world(db):
    """Owner and organizer in a family; owner's list granted to it."""
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
    gift_list = _mklist(db, owner, "Owner's List")
    db.add(ListFamilyShare(list_id=gift_list.id, family_id=family.id))
    db.flush()
    return SimpleNamespace(
        organizer=organizer, owner=owner, family=family, gift_list=gift_list
    )


def test_leaving_a_family_deletes_the_departing_members_grants(
    client, db, granted_world
):
    w = granted_world
    resp = client.delete(
        f"/families/{w.family.id}/members/{w.owner.id}", headers=_auth(w.owner)
    )
    assert resp.status_code == 204
    assert _granted(db, w.gift_list.id) == set()

    fam = client.get("/lists?filter=family", headers=_auth(w.organizer)).json()
    assert "Owner's List" not in {l["name"] for l in fam}


def test_being_removed_deletes_the_departing_members_grants(client, db, granted_world):
    w = granted_world
    resp = client.delete(
        f"/families/{w.family.id}/members/{w.owner.id}", headers=_auth(w.organizer)
    )
    assert resp.status_code == 204
    assert _granted(db, w.gift_list.id) == set()


def test_removal_leaves_a_co_members_grants_alone(client, db, granted_world):
    w = granted_world
    organizer_list = _mklist(db, w.organizer, "Organizer's List")
    db.add(ListFamilyShare(list_id=organizer_list.id, family_id=w.family.id))
    db.flush()

    client.delete(
        f"/families/{w.family.id}/members/{w.owner.id}", headers=_auth(w.organizer)
    )
    assert _granted(db, organizer_list.id) == {w.family.id}


def test_deleting_a_family_deletes_all_of_its_grants(client, db, granted_world):
    w = granted_world
    resp = client.delete(f"/families/{w.family.id}", headers=_auth(w.organizer))
    assert resp.status_code == 204
    assert _granted(db, w.gift_list.id) == set()


def test_leaving_one_family_leaves_grants_on_another_intact(client, db, granted_world):
    w = granted_world
    other = Family(name="The Smiths", created_by_id=w.owner.id)
    db.add(other)
    db.flush()
    db.add(FamilyMember(family_id=other.id, user_id=w.owner.id, role="organizer"))
    db.add(ListFamilyShare(list_id=w.gift_list.id, family_id=other.id))
    db.flush()

    client.delete(
        f"/families/{w.family.id}/members/{w.owner.id}", headers=_auth(w.owner)
    )
    assert _granted(db, w.gift_list.id) == {other.id}
