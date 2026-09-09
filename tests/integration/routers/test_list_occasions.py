"""Share-to-an-occasion: creation behavior, the share management API, the
archived-occasion rules, and the claim handling on revoke (NEU-1265)."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.dependencies import create_access_token
from app.models.claim import Claim
from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_occasion_share import ListOccasionShare
from app.models.list_share import ListShare
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


def _mkoccasion(db, family, name, created_by, is_archived=False):
    occasion = Occasion(
        family_id=family.id,
        name=name,
        created_by_id=created_by.id,
        is_archived=is_archived,
    )
    db.add(occasion)
    db.flush()
    return occasion


def _shared(db, list_id):
    return {
        row.occasion_id
        for row in db.query(ListOccasionShare).filter_by(list_id=list_id).all()
    }


@pytest.fixture
def world(db):
    """Owner + Rel + Cousin, in two families: Boones {owner, rel} and Smiths
    {owner, cousin}, each running one active occasion."""
    owner = _mkuser(db, "owner@test.com", "Owner")
    rel = _mkuser(db, "rel@test.com", "Relative")
    cousin = _mkuser(db, "cousin@test.com", "Cousin")
    boones = _mkfamily(db, "The Boones", owner, rel)
    smiths = _mkfamily(db, "The Smiths", owner, cousin)
    boones_xmas = _mkoccasion(db, boones, "Christmas 2026", owner)
    smiths_xmas = _mkoccasion(db, smiths, "Christmas 2026", owner)
    return SimpleNamespace(
        owner=owner,
        rel=rel,
        cousin=cousin,
        boones=boones,
        smiths=smiths,
        boones_xmas=boones_xmas,
        smiths_xmas=smiths_xmas,
    )


# ---------------------------------------------------------------------------
# Creation behavior
# ---------------------------------------------------------------------------


def test_create_with_no_occasions_shares_with_none(client, db, world):
    resp = client.post(
        "/lists", headers=_auth(world.owner), json={"name": "Private"}
    )
    assert resp.status_code == 201
    assert _shared(db, resp.json()["id"]) == set()

    # And it is invisible in a co-member's shared scope.
    shared = client.get("/lists?filter=shared", headers=_auth(world.rel)).json()
    assert "Private" not in {l["name"] for l in shared}


def test_create_with_occasion_ids_shares_with_exactly_those(client, db, world):
    resp = client.post(
        "/lists",
        headers=_auth(world.owner),
        json={"name": "Birthday", "occasion_ids": [world.boones_xmas.id]},
    )
    assert resp.status_code == 201
    assert _shared(db, resp.json()["id"]) == {world.boones_xmas.id}

    rel_view = client.get("/lists?filter=shared", headers=_auth(world.rel)).json()
    entry = next(l for l in rel_view if l["name"] == "Birthday")
    assert entry["shared_via"] == {
        "kind": "occasion",
        "id": world.boones_xmas.id,
        "name": "Christmas 2026",
        "family": {"id": world.boones.id, "name": "The Boones"},
    }

    cousin_view = client.get("/lists?filter=shared", headers=_auth(world.cousin)).json()
    assert "Birthday" not in {l["name"] for l in cousin_view}


def test_create_with_an_occasion_the_caller_is_not_in_returns_403(client, db, world):
    outsider = _mkuser(db, "out@test.com", "Outsider")
    other = _mkfamily(db, "Other Family", outsider)
    other_occasion = _mkoccasion(db, other, "Their Christmas", outsider)

    resp = client.post(
        "/lists",
        headers=_auth(world.owner),
        json={"name": "Nope", "occasion_ids": [other_occasion.id]},
    )
    assert resp.status_code == 403


def test_create_with_an_archived_occasion_returns_409(client, db, world):
    archived = _mkoccasion(db, world.boones, "Christmas 2025", world.owner, True)

    resp = client.post(
        "/lists",
        headers=_auth(world.owner),
        json={"name": "Nope", "occasion_ids": [archived.id]},
    )
    assert resp.status_code == 409


def test_create_with_a_foreign_occasion_writes_no_partial_shares(client, db, world):
    """A foreign id partway through the list must not leave the earlier shares
    written — validation runs over every id before any share is created."""
    outsider = _mkuser(db, "out@test.com", "Outsider")
    other = _mkfamily(db, "Other Family", outsider)
    other_occasion = _mkoccasion(db, other, "Their Christmas", outsider)

    resp = client.post(
        "/lists",
        headers=_auth(world.owner),
        json={
            "name": "Nope",
            "occasion_ids": [world.boones_xmas.id, other_occasion.id],
        },
    )
    assert resp.status_code == 403
    assert (
        db.query(ListOccasionShare).filter_by(occasion_id=world.boones_xmas.id).count()
        == 0
    )


# ---------------------------------------------------------------------------
# The sharing control's families half
# ---------------------------------------------------------------------------


@pytest.fixture
def owned_list(db, world):
    gift_list = GiftList(name="Owner's List", owner_id=world.owner.id)
    db.add(gift_list)
    db.flush()
    return gift_list


def test_get_lists_every_family_with_its_occasions_and_shared_flags(
    client, db, world, owned_list
):
    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=world.boones_xmas.id))
    db.flush()

    resp = client.get(
        f"/lists/{owned_list.id}/families", headers=_auth(world.owner)
    )
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "id": world.boones.id,
            "name": "The Boones",
            "occasions": [
                {
                    "id": world.boones_xmas.id,
                    "name": "Christmas 2026",
                    "is_archived": False,
                    "shared": True,
                }
            ],
        },
        {
            "id": world.smiths.id,
            "name": "The Smiths",
            "occasions": [
                {
                    "id": world.smiths_xmas.id,
                    "name": "Christmas 2026",
                    "is_archived": False,
                    "shared": False,
                }
            ],
        },
    ]


def test_get_lists_a_family_with_no_active_occasion_as_an_empty_list(
    client, db, world, owned_list
):
    """The "no active occasion" state: the family is still listed, because the
    control renders it disabled with the reason rather than hiding it."""
    workmates = _mkfamily(db, "Work Friends", world.owner)

    resp = client.get(f"/lists/{owned_list.id}/families", headers=_auth(world.owner))
    row = next(f for f in resp.json() if f["id"] == workmates.id)
    assert row["occasions"] == []


def test_get_lists_an_archived_occasion_only_when_already_shared_to_it(
    client, db, world, owned_list
):
    archived = _mkoccasion(db, world.boones, "Christmas 2025", world.owner, True)

    resp = client.get(f"/lists/{owned_list.id}/families", headers=_auth(world.owner))
    boones = next(f for f in resp.json() if f["id"] == world.boones.id)
    assert archived.id not in {o["id"] for o in boones["occasions"]}

    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=archived.id))
    db.flush()

    resp = client.get(f"/lists/{owned_list.id}/families", headers=_auth(world.owner))
    boones = next(f for f in resp.json() if f["id"] == world.boones.id)
    assert {
        "id": archived.id,
        "name": "Christmas 2025",
        "is_archived": True,
        "shared": True,
    } in boones["occasions"]


def test_get_forbidden_for_non_owner(client, world, owned_list):
    resp = client.get(f"/lists/{owned_list.id}/families", headers=_auth(world.rel))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Share management API
# ---------------------------------------------------------------------------


def test_put_creates_the_share(client, db, world, owned_list):
    resp = client.put(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    assert _shared(db, owned_list.id) == {world.boones_xmas.id}


def test_put_is_idempotent(client, db, world, owned_list):
    url = f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}"
    assert client.put(url, headers=_auth(world.owner)).status_code == 204
    assert client.put(url, headers=_auth(world.owner)).status_code == 204
    assert _shared(db, owned_list.id) == {world.boones_xmas.id}


def test_put_for_an_occasion_the_owner_is_not_a_member_of_returns_403(
    client, db, world, owned_list
):
    outsider = _mkuser(db, "out@test.com", "Outsider")
    other = _mkfamily(db, "Other Family", outsider)
    other_occasion = _mkoccasion(db, other, "Their Christmas", outsider)

    resp = client.put(
        f"/lists/{owned_list.id}/occasions/{other_occasion.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 403


def test_put_for_an_occasion_that_does_not_exist_returns_404(
    client, world, owned_list
):
    resp = client.put(
        f"/lists/{owned_list.id}/occasions/999999", headers=_auth(world.owner)
    )
    assert resp.status_code == 404


def test_put_for_an_archived_occasion_returns_409(client, db, world, owned_list):
    """Archiving blocks new shares, and only that (ADR 0002 §5.4)."""
    archived = _mkoccasion(db, world.boones, "Christmas 2025", world.owner, True)

    resp = client.put(
        f"/lists/{owned_list.id}/occasions/{archived.id}", headers=_auth(world.owner)
    )
    assert resp.status_code == 409
    assert _shared(db, owned_list.id) == set()


def test_put_on_an_archived_occasion_already_shared_to_stays_a_noop_204(
    client, db, world, owned_list
):
    """Re-issuing an existing share must not turn into a 409 just because the
    occasion has been archived since — nothing about the list changes."""
    archived = _mkoccasion(db, world.boones, "Christmas 2025", world.owner, True)
    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=archived.id))
    db.flush()

    resp = client.put(
        f"/lists/{owned_list.id}/occasions/{archived.id}", headers=_auth(world.owner)
    )
    assert resp.status_code == 204
    assert _shared(db, owned_list.id) == {archived.id}


def test_toggling_on_grants_visibility_immediately(client, db, world, owned_list):
    client.put(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}",
        headers=_auth(world.owner),
    )
    assert client.get(
        f"/lists/{owned_list.id}", headers=_auth(world.rel)
    ).status_code == 200

    client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}",
        headers=_auth(world.owner),
    )
    assert client.get(
        f"/lists/{owned_list.id}", headers=_auth(world.rel)
    ).status_code == 403


# ---------------------------------------------------------------------------
# Revoking a share: claims
# ---------------------------------------------------------------------------


@pytest.fixture
def claimed(db, world, owned_list):
    """Owner's list shared to the Boones' occasion, with a gift claimed by rel
    and a folder item pointing at it from rel's folder."""
    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=world.boones_xmas.id))
    gift = Gift(list_id=owned_list.id, name="A Book")
    db.add(gift)
    folder = Folder(name="Rel's Shopping", owner_id=world.rel.id)
    db.add(folder)
    db.flush()
    db.add(
        Claim(
            gift_id=gift.id, user_id=world.rel.id, claimed_at=datetime.now(timezone.utc)
        )
    )
    db.flush()
    db.add(FolderItem(folder_id=folder.id, list_id=owned_list.id))
    db.flush()
    return SimpleNamespace(gift=gift, folder=folder)


def _items(db, folder_id):
    return db.query(FolderItem).filter_by(folder_id=folder_id).count()


def _claimer_id(db, gift):
    """Who holds the claim on this gift, if anyone. The answer moved off the
    gift row and onto `claims` (ADR 0003)."""
    db.expire_all()
    claim = db.query(Claim).filter_by(gift_id=gift.id).one_or_none()
    return claim.user_id if claim else None


def test_revoke_with_no_affected_claims_returns_204(client, db, world, owned_list):
    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=world.boones_xmas.id))
    db.add(Gift(list_id=owned_list.id, name="Unclaimed"))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    assert _shared(db, owned_list.id) == set()


def test_revoke_with_a_claim_returns_409_and_changes_nothing(
    client, db, world, owned_list, claimed
):
    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail == "Some gifts on this list are claimed by members of this family."
    # No count, no gift name, no claimer name.
    assert "A Book" not in detail
    assert world.rel.name not in detail

    assert _shared(db, owned_list.id) == {world.boones_xmas.id}
    db.refresh(claimed.gift)
    assert _claimer_id(db, claimed.gift) == world.rel.id
    assert _items(db, claimed.folder.id) == 1


def test_revoke_claims_release_unclaims_and_drops_folder_items(
    client, db, world, owned_list, claimed
):
    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}?claims=release",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    assert _shared(db, owned_list.id) == set()
    db.refresh(claimed.gift)
    # The claim row goes entirely, taking its purchase state with it.
    assert _claimer_id(db, claimed.gift) is None
    assert claimed.gift.claim is None
    assert _items(db, claimed.folder.id) == 0


def test_revoke_claims_keep_leaves_the_claim_but_drops_folder_items(
    client, db, world, owned_list, claimed
):
    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}?claims=keep",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    assert _shared(db, owned_list.id) == set()
    db.refresh(claimed.gift)
    assert _claimer_id(db, claimed.gift) == world.rel.id
    assert _items(db, claimed.folder.id) == 0


def test_revoke_release_spares_a_claimer_who_still_has_a_list_share(
    client, db, world, owned_list, claimed
):
    db.add(ListShare(list_id=owned_list.id, user_id=world.rel.id))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}?claims=release",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    db.refresh(claimed.gift)
    assert _claimer_id(db, claimed.gift) == world.rel.id
    assert _items(db, claimed.folder.id) == 1


def test_revoke_release_spares_a_claimer_who_sees_it_via_another_family(
    client, db, world, owned_list, claimed
):
    # rel also belongs to the Smiths, whose occasion the list is shared to too.
    db.add(FamilyMember(family_id=world.smiths.id, user_id=world.rel.id, role="member"))
    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=world.smiths_xmas.id))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}?claims=release",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    db.refresh(claimed.gift)
    assert _claimer_id(db, claimed.gift) == world.rel.id
    assert _items(db, claimed.folder.id) == 1


def test_revoke_release_spares_a_claimer_reached_by_a_sibling_occasion(
    client, db, world, owned_list, claimed
):
    """Two occasions on the *same* family: revoking one leaves the other, so
    nobody in that family loses access and no claim is released."""
    sibling = _mkoccasion(db, world.boones, "Gran's 80th", world.owner)
    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=sibling.id))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}?claims=release",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    db.refresh(claimed.gift)
    assert _claimer_id(db, claimed.gift) == world.rel.id
    assert _items(db, claimed.folder.id) == 1


def test_revoke_without_claims_is_not_blocked_by_a_claimer_who_keeps_access(
    client, db, world, owned_list, claimed
):
    db.add(ListShare(list_id=owned_list.id, user_id=world.rel.id))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204


def test_revoke_ignores_the_owners_own_claim(client, db, world, owned_list):
    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=world.boones_xmas.id))
    gift = Gift(list_id=owned_list.id, name="Self")
    db.add(gift)
    db.flush()
    db.add(
        Claim(
            gift_id=gift.id,
            user_id=world.owner.id,
            claimed_at=datetime.now(timezone.utc),
        )
    )
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204


def test_revoke_works_on_an_archived_occasion(client, db, world, owned_list):
    """Unsharing an archived occasion stays possible: archiving blocks new
    shares, it does not freeze the old ones in place."""
    archived = _mkoccasion(db, world.boones, "Christmas 2025", world.owner, True)
    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=archived.id))
    db.flush()

    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{archived.id}", headers=_auth(world.owner)
    )
    assert resp.status_code == 204
    assert _shared(db, owned_list.id) == set()


def test_revoking_a_share_that_does_not_exist_is_a_noop(client, world, owned_list):
    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204


def test_invalid_claims_value_is_rejected(client, world, owned_list):
    resp = client.delete(
        f"/lists/{owned_list.id}/occasions/{world.boones_xmas.id}?claims=nonsense",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Deleting a list drops its shares
# ---------------------------------------------------------------------------


def test_deleting_a_list_deletes_its_shares(client, db, world, owned_list):
    db.add(ListOccasionShare(list_id=owned_list.id, occasion_id=world.boones_xmas.id))
    db.flush()
    list_id = owned_list.id

    assert client.delete(
        f"/lists/{list_id}", headers=_auth(world.owner)
    ).status_code == 204
    assert _shared(db, list_id) == set()
