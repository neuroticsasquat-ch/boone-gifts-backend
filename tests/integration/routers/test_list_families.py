"""Per-family list sharing: creation behavior, the grant management API,
membership hooks, and the claim handling on revoke (NEU-1202)."""
from types import SimpleNamespace

import pytest

from app.dependencies import create_access_token
from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_family_share import ListFamilyShare
from app.models.list_share import ListShare
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


def _mkfamily(db, name, *members):
    family = Family(name=name, created_by_id=members[0].id)
    db.add(family)
    db.flush()
    db.add_all(
        [
            FamilyMember(
                family_id=family.id,
                user_id=user.id,
                role="organizer" if i == 0 else "member",
            )
            for i, user in enumerate(members)
        ]
    )
    db.flush()
    return family


def _granted(db, list_id):
    return {
        row.family_id
        for row in db.query(ListFamilyShare).filter_by(list_id=list_id).all()
    }


@pytest.fixture
def world(db):
    """Owner (full mode) + Rel, in two families: Boones {owner, rel} and
    Smiths {owner, cousin}."""
    owner = _mkuser(db, "owner@test.com", "Owner")
    rel = _mkuser(db, "rel@test.com", "Relative")
    cousin = _mkuser(db, "cousin@test.com", "Cousin")
    boones = _mkfamily(db, "The Boones", owner, rel)
    smiths = _mkfamily(db, "The Smiths", owner, cousin)
    return SimpleNamespace(
        owner=owner, rel=rel, cousin=cousin, boones=boones, smiths=smiths
    )


# ---------------------------------------------------------------------------
# Creation behavior (§2.4)
# ---------------------------------------------------------------------------


def test_full_mode_create_with_no_families_shares_with_none(client, db, world):
    resp = client.post(
        "/lists", headers=_auth(world.owner), json={"name": "Private"}
    )
    assert resp.status_code == 201
    assert _granted(db, resp.json()["id"]) == set()

    # And it is invisible to a co-member's family view.
    fam = client.get("/lists?filter=family", headers=_auth(world.rel)).json()
    assert "Private" not in {l["name"] for l in fam}


def test_full_mode_create_with_family_ids_shares_with_exactly_those(client, db, world):
    resp = client.post(
        "/lists",
        headers=_auth(world.owner),
        json={"name": "Birthday", "family_ids": [world.boones.id]},
    )
    assert resp.status_code == 201
    assert _granted(db, resp.json()["id"]) == {world.boones.id}

    rel_view = client.get("/lists?filter=family", headers=_auth(world.rel)).json()
    entry = next(l for l in rel_view if l["name"] == "Birthday")
    assert [f["name"] for f in entry["families"]] == ["The Boones"]

    cousin_view = client.get("/lists?filter=family", headers=_auth(world.cousin)).json()
    assert "Birthday" not in {l["name"] for l in cousin_view}


def test_create_with_a_family_the_caller_is_not_in_returns_403(client, db, world):
    outsider = _mkuser(db, "out@test.com", "Outsider")
    other = _mkfamily(db, "Other Family", outsider)

    resp = client.post(
        "/lists",
        headers=_auth(world.owner),
        json={"name": "Nope", "family_ids": [other.id]},
    )
    assert resp.status_code == 403


def test_simple_mode_create_shares_with_all_families(client, db, world):
    world.owner.simple_mode = True
    db.flush()

    resp = client.post("/lists", headers=_auth(world.owner), json={"name": "Auto"})
    assert resp.status_code == 201
    assert _granted(db, resp.json()["id"]) == {world.boones.id, world.smiths.id}


def test_simple_mode_create_ignores_family_ids_in_the_body(client, db, world):
    world.owner.simple_mode = True
    db.flush()

    resp = client.post(
        "/lists",
        headers=_auth(world.owner),
        json={"name": "Auto", "family_ids": []},
    )
    assert resp.status_code == 201
    assert _granted(db, resp.json()["id"]) == {world.boones.id, world.smiths.id}


# ---------------------------------------------------------------------------
# Grant management API (§2.6)
# ---------------------------------------------------------------------------


@pytest.fixture
def owned_list(db, world):
    gift_list = GiftList(name="Owner's List", owner_id=world.owner.id)
    db.add(gift_list)
    db.flush()
    return gift_list


def test_get_lists_every_family_the_owner_belongs_to_with_shared_flag(
    client, db, world, owned_list
):
    db.add(ListFamilyShare(list_id=owned_list.id, family_id=world.boones.id))
    db.flush()

    resp = client.get(
        f"/lists/{owned_list.id}/families", headers=_auth(world.owner)
    )
    assert resp.status_code == 200
    assert resp.json() == [
        {"id": world.boones.id, "name": "The Boones", "shared": True},
        {"id": world.smiths.id, "name": "The Smiths", "shared": False},
    ]


def test_get_is_readable_in_simple_mode(client, db, world, owned_list):
    world.owner.simple_mode = True
    db.flush()
    resp = client.get(f"/lists/{owned_list.id}/families", headers=_auth(world.owner))
    assert resp.status_code == 200
    assert [f["shared"] for f in resp.json()] == [False, False]


def test_get_forbidden_for_non_owner(client, world, owned_list):
    resp = client.get(f"/lists/{owned_list.id}/families", headers=_auth(world.rel))
    assert resp.status_code == 403


def test_put_creates_the_grant(client, db, world, owned_list):
    resp = client.put(
        f"/lists/{owned_list.id}/families/{world.boones.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    assert _granted(db, owned_list.id) == {world.boones.id}


def test_put_is_idempotent(client, db, world, owned_list):
    url = f"/lists/{owned_list.id}/families/{world.boones.id}"
    assert client.put(url, headers=_auth(world.owner)).status_code == 204
    assert client.put(url, headers=_auth(world.owner)).status_code == 204
    assert _granted(db, owned_list.id) == {world.boones.id}


def test_put_for_a_family_the_owner_is_not_in_returns_403(client, db, world, owned_list):
    outsider = _mkuser(db, "out@test.com", "Outsider")
    other = _mkfamily(db, "Other Family", outsider)

    resp = client.put(
        f"/lists/{owned_list.id}/families/{other.id}", headers=_auth(world.owner)
    )
    assert resp.status_code == 403


def test_toggling_on_grants_visibility_immediately(client, db, world, owned_list):
    client.put(
        f"/lists/{owned_list.id}/families/{world.boones.id}",
        headers=_auth(world.owner),
    )
    assert client.get(
        f"/lists/{owned_list.id}", headers=_auth(world.rel)
    ).status_code == 200

    client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}",
        headers=_auth(world.owner),
    )
    assert client.get(
        f"/lists/{owned_list.id}", headers=_auth(world.rel)
    ).status_code == 403


def test_put_and_delete_forbidden_in_simple_mode(client, db, world, owned_list):
    db.add(ListFamilyShare(list_id=owned_list.id, family_id=world.boones.id))
    world.owner.simple_mode = True
    db.flush()
    headers = _auth(world.owner)
    url = f"/lists/{owned_list.id}/families/{world.boones.id}"

    put = client.put(url, headers=headers)
    assert put.status_code == 403
    assert put.json()["detail"] == (
        "Switch to full mode to manage family sharing for this list."
    )

    delete = client.delete(url, headers=headers)
    assert delete.status_code == 403
    assert delete.json()["detail"] == (
        "Switch to full mode to manage family sharing for this list."
    )
    assert _granted(db, owned_list.id) == {world.boones.id}


# ---------------------------------------------------------------------------
# Revoking a grant: claims (§2.7)
# ---------------------------------------------------------------------------


@pytest.fixture
def claimed(db, world, owned_list):
    """Owner's list granted to the Boones, with a gift claimed by rel and a
    collection item pointing at it from rel's collection."""
    db.add(ListFamilyShare(list_id=owned_list.id, family_id=world.boones.id))
    gift = Gift(list_id=owned_list.id, name="A Book", claimed_by_id=world.rel.id)
    db.add(gift)
    collection = Collection(name="Rel's Shopping", owner_id=world.rel.id)
    db.add(collection)
    db.flush()
    db.add(CollectionItem(collection_id=collection.id, list_id=owned_list.id))
    db.flush()
    return SimpleNamespace(gift=gift, collection=collection)


def _items(db, collection_id):
    return db.query(CollectionItem).filter_by(collection_id=collection_id).count()


def test_revoke_with_no_affected_claims_returns_204(client, db, world, owned_list):
    db.add(ListFamilyShare(list_id=owned_list.id, family_id=world.boones.id))
    db.add(Gift(list_id=owned_list.id, name="Unclaimed"))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    assert _granted(db, owned_list.id) == set()


def test_revoke_with_a_claim_returns_409_and_changes_nothing(
    client, db, world, owned_list, claimed
):
    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail == "Some gifts on this list are claimed by members of this family."
    # No count, no gift name, no claimer name.
    assert "A Book" not in detail
    assert world.rel.name not in detail

    assert _granted(db, owned_list.id) == {world.boones.id}
    db.refresh(claimed.gift)
    assert claimed.gift.claimed_by_id == world.rel.id
    assert _items(db, claimed.collection.id) == 1


def test_revoke_claims_release_unclaims_and_drops_collection_items(
    client, db, world, owned_list, claimed
):
    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}?claims=release",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    assert _granted(db, owned_list.id) == set()
    db.refresh(claimed.gift)
    assert claimed.gift.claimed_by_id is None
    assert claimed.gift.claimed_at is None
    assert _items(db, claimed.collection.id) == 0


def test_revoke_claims_keep_leaves_the_claim_but_drops_collection_items(
    client, db, world, owned_list, claimed
):
    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}?claims=keep",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    assert _granted(db, owned_list.id) == set()
    db.refresh(claimed.gift)
    assert claimed.gift.claimed_by_id == world.rel.id
    assert _items(db, claimed.collection.id) == 0


def test_revoke_release_spares_a_claimer_who_still_has_a_list_share(
    client, db, world, owned_list, claimed
):
    db.add(ListShare(list_id=owned_list.id, user_id=world.rel.id))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}?claims=release",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    db.refresh(claimed.gift)
    assert claimed.gift.claimed_by_id == world.rel.id
    assert _items(db, claimed.collection.id) == 1


def test_revoke_release_spares_a_claimer_who_sees_it_via_another_family(
    client, db, world, owned_list, claimed
):
    # rel also belongs to the Smiths, which the list is granted to as well.
    db.add(FamilyMember(family_id=world.smiths.id, user_id=world.rel.id, role="member"))
    db.add(ListFamilyShare(list_id=owned_list.id, family_id=world.smiths.id))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}?claims=release",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    db.refresh(claimed.gift)
    assert claimed.gift.claimed_by_id == world.rel.id
    assert _items(db, claimed.collection.id) == 1


def test_revoke_without_claims_is_not_blocked_by_a_claimer_who_keeps_access(
    client, db, world, owned_list, claimed
):
    db.add(ListShare(list_id=owned_list.id, user_id=world.rel.id))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204


def test_revoke_ignores_the_owners_own_claim(client, db, world, owned_list):
    db.add(ListFamilyShare(list_id=owned_list.id, family_id=world.boones.id))
    db.add(Gift(list_id=owned_list.id, name="Self", claimed_by_id=world.owner.id))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204


def test_revoking_a_grant_that_does_not_exist_is_a_noop(client, world, owned_list):
    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204


def test_invalid_claims_value_is_rejected(client, world, owned_list):
    resp = client.delete(
        f"/lists/{owned_list.id}/families/{world.boones.id}?claims=nonsense",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Deleting a list drops its grants (§2.3)
# ---------------------------------------------------------------------------


def test_deleting_a_list_deletes_its_grants(client, db, world, owned_list):
    db.add(ListFamilyShare(list_id=owned_list.id, family_id=world.boones.id))
    db.flush()
    list_id = owned_list.id

    assert client.delete(
        f"/lists/{list_id}", headers=_auth(world.owner)
    ).status_code == 204
    assert _granted(db, list_id) == set()
