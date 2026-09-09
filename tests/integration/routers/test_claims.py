"""Claim filing and candidates (NEU-1269).

Every claim lands in exactly one budget without putting a decision in front of
the user on the app's hottest path. That rests on two derived sets — `allowed`
wide enough that a misfiling stays fixable, `suggested` narrow enough that the
prompt stays rare — so most of what is asserted here is the difference between
them.
"""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.dependencies import create_access_token
from app.models.claim import Claim
from app.models.connection import Connection
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


def _mklist(db, owner, name="Wishlist", *occasions):
    gift_list = GiftList(name=name, owner_id=owner.id)
    db.add(gift_list)
    db.flush()
    db.add_all(
        [
            ListOccasionShare(list_id=gift_list.id, occasion_id=o.id)
            for o in occasions
        ]
    )
    db.flush()
    return gift_list


def _mkgift(db, gift_list, name="Socks"):
    gift = Gift(list_id=gift_list.id, name=name)
    db.add(gift)
    db.flush()
    return gift


def _mkclaim(db, gift, claimer, occasion=None):
    claim = Claim(
        gift_id=gift.id,
        user_id=claimer.id,
        occasion_id=occasion.id if occasion else None,
        claimed_at=datetime.now(timezone.utc),
    )
    db.add(claim)
    db.flush()
    return claim


@pytest.fixture
def world(db):
    """Owner and Claimer in one family running Christmas 2026 (active).

    Deliberately one active occasion: the silent-filing case is the common one,
    and every other shape in this file is built by adding to it.
    """
    owner = _mkuser(db, "owner@test.com", "Owner")
    claimer = _mkuser(db, "claimer@test.com", "Claimer")
    boones = _mkfamily(db, "The Boones", owner, claimer)
    xmas = _mkoccasion(db, boones, "Christmas 2026", owner)
    gift_list = _mklist(db, owner, "Wishlist", xmas)
    return SimpleNamespace(
        owner=owner,
        claimer=claimer,
        boones=boones,
        xmas=xmas,
        list=gift_list,
        gift=_mkgift(db, gift_list),
    )


def _claim(client, world, gift=None, json=None, user=None):
    gift = gift or world.gift
    return client.post(
        f"/lists/{world.list.id}/gifts/{gift.id}/claim",
        headers=_auth(user or world.claimer),
        json=json,
    )


# ---------------------------------------------------------------------------
# POST .../claim — resolving the filing
# ---------------------------------------------------------------------------


def test_no_suggestions_files_under_nothing(client, db, world):
    # Reachable directly rather than through an occasion, so nothing is shared
    # to file under.
    private = _mklist(db, world.owner, "Direct")
    db.add(ListShare(list_id=private.id, user_id=world.claimer.id))
    db.flush()
    gift = _mkgift(db, private, "Mug")

    resp = client.post(
        f"/lists/{private.id}/gifts/{gift.id}/claim", headers=_auth(world.claimer)
    )
    assert resp.status_code == 201
    assert resp.json()["occasion_id"] is None


def test_one_suggestion_files_silently(client, db, world):
    resp = _claim(client, world)
    assert resp.status_code == 201
    assert resp.json()["occasion_id"] == world.xmas.id
    stored = db.query(Claim).filter_by(gift_id=world.gift.id).one()
    assert stored.occasion_id == world.xmas.id


def test_two_suggestions_and_no_id_is_a_400_with_no_claim(client, db, world):
    smiths = _mkfamily(db, "The Smiths", world.owner, world.claimer)
    smiths_xmas = _mkoccasion(db, smiths, "Christmas 2026", world.owner)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=smiths_xmas.id))
    db.flush()

    resp = _claim(client, world)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "ambiguous_occasion"
    # The gift is still there to be claimed — a refused filing must not have
    # written a half-made claim.
    assert db.query(Claim).filter_by(gift_id=world.gift.id).count() == 0


def test_an_explicit_allowed_id_is_honoured(client, db, world):
    grans = _mkoccasion(db, world.boones, "Gran's 80th", world.owner)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=grans.id))
    db.flush()

    resp = _claim(client, world, json={"occasion_id": grans.id})
    assert resp.status_code == 201
    assert resp.json()["occasion_id"] == grans.id


def test_an_explicit_archived_id_is_honoured(client, db, world):
    """`allowed` includes archived occasions, so a late claim can still be filed
    under the Christmas it was actually for."""
    world.xmas.is_archived = True
    grans = _mkoccasion(db, world.boones, "Gran's 80th", world.owner)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=grans.id))
    db.flush()

    resp = _claim(client, world, json={"occasion_id": world.xmas.id})
    assert resp.status_code == 201
    assert resp.json()["occasion_id"] == world.xmas.id


def test_an_id_outside_allowed_still_creates_the_claim(client, db, world):
    """A share revoked between the client's read and the user's click. Claiming
    is competitive: failing here would hand the gift to whoever clicks next, for
    a reason nobody but the claimer can see."""
    others = _mkfamily(db, "The Others", world.owner)
    foreign = _mkoccasion(db, others, "Not Yours", world.owner)

    resp = _claim(client, world, json={"occasion_id": foreign.id})
    assert resp.status_code == 201
    # Falls back to the single suggestion rather than refusing.
    assert resp.json()["occasion_id"] == world.xmas.id


def test_an_id_outside_allowed_never_produces_the_ambiguous_400(client, db, world):
    smiths = _mkfamily(db, "The Smiths", world.owner, world.claimer)
    smiths_xmas = _mkoccasion(db, smiths, "Christmas 2026", world.owner)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=smiths_xmas.id))
    db.flush()

    resp = _claim(client, world, json={"occasion_id": 999_999})
    # The client did prompt; its answer merely went stale. The claim stands
    # unfiled, and PATCH is the correction path.
    assert resp.status_code == 201
    assert resp.json()["occasion_id"] is None


def test_an_explicit_null_files_under_nothing(client, db, world):
    resp = _claim(client, world, json={"occasion_id": None})
    assert resp.status_code == 201
    # An explicit null is a choice, not an omission: it must not auto-pick the
    # one suggestion.
    assert resp.json()["occasion_id"] is None


def test_the_year_three_case_files_silently(client, db, world):
    """Two archived Christmases and one active. Without `suggested` narrowing to
    active, every claim would prompt forever with the right answer obvious every
    time — and it is invisible in a fresh test database."""
    world.xmas.is_archived = True
    xmas_2027 = _mkoccasion(
        db, world.boones, "Christmas 2027", world.owner, is_archived=True
    )
    xmas_2028 = _mkoccasion(db, world.boones, "Christmas 2028", world.owner)
    for occasion in (xmas_2027, xmas_2028):
        db.add(ListOccasionShare(list_id=world.list.id, occasion_id=occasion.id))
    db.flush()

    resp = _claim(client, world)
    assert resp.status_code == 201
    assert resp.json()["occasion_id"] == xmas_2028.id


def test_the_jan_8_case_files_under_the_active_occasion(client, db, world):
    """Christmas archived on Jan 2, Gran's 80th active, a Christmas present
    claimed Jan 8. It files under Gran's — and §2.2 is what lets the user move
    it back."""
    world.xmas.is_archived = True
    grans = _mkoccasion(db, world.boones, "Gran's 80th", world.owner)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=grans.id))
    db.flush()

    resp = _claim(client, world)
    assert resp.status_code == 201
    assert resp.json()["occasion_id"] == grans.id

    claim_id = db.query(Claim).filter_by(gift_id=world.gift.id).one().id
    moved = client.patch(
        f"/claims/{claim_id}",
        headers=_auth(world.claimer),
        json={"occasion_id": world.xmas.id},
    )
    assert moved.status_code == 200
    assert moved.json()["occasion_id"] == world.xmas.id


def test_all_occasions_archived_still_yields_one_suggestion(client, db, world):
    """The `else allowed` fallback: the late shopper's list is shared only to an
    archived occasion, and the January purchase must still file correctly."""
    world.xmas.is_archived = True
    db.flush()

    resp = _claim(client, world)
    assert resp.status_code == 201
    assert resp.json()["occasion_id"] == world.xmas.id


def test_two_archived_occasions_and_no_active_one_prompts(client, db, world):
    world.xmas.is_archived = True
    other = _mkoccasion(db, world.boones, "Gran's 80th", world.owner, is_archived=True)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=other.id))
    db.flush()

    resp = _claim(client, world)
    assert resp.status_code == 400


def test_an_occasion_on_a_family_the_claimer_is_not_in_is_not_suggested(
    client, db, world
):
    """`allowed` is bounded by the claimer's own memberships, not the owner's."""
    smiths = _mkfamily(db, "The Smiths", world.owner)
    smiths_xmas = _mkoccasion(db, smiths, "Christmas 2026", world.owner)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=smiths_xmas.id))
    db.flush()

    # Two shares, but only one of them is on a family the claimer belongs to,
    # so there is nothing ambiguous about it.
    resp = _claim(client, world)
    assert resp.status_code == 201
    assert resp.json()["occasion_id"] == world.xmas.id


# ---------------------------------------------------------------------------
# The archived matrix (§6)
# ---------------------------------------------------------------------------

# shape -> (occasions to share the list to, expected `allowed`, expected
# `suggested`). Named by what the family looks like, because that is what
# decides whether the user is asked anything.
MATRIX = [
    ("no occasions", [], [], []),
    ("one active", ["A"], ["A"], ["A"]),
    ("one archived", ["X"], ["X"], ["X"]),
    ("one of each", ["A", "X"], ["A", "X"], ["A"]),
    ("two active", ["A", "A"], ["A", "A"], ["A", "A"]),
    ("two archived", ["X", "X"], ["X", "X"], ["X", "X"]),
]


@pytest.mark.parametrize(
    "shape,shared,expected_allowed,expected_suggested",
    MATRIX,
    ids=[row[0] for row in MATRIX],
)
def test_the_archived_matrix(
    client, db, world, shape, shared, expected_allowed, expected_suggested
):
    """Both sets, for every combination of active and archived occasions — and
    the rule that ties them to the user's experience: the prompt fires exactly
    when two or more are suggested, and never otherwise."""
    occasions = [
        _mkoccasion(
            db,
            world.boones,
            f"{shape} {index}",
            world.owner,
            is_archived=(kind == "X"),
        )
        for index, kind in enumerate(shared)
    ]
    gift_list = _mklist(db, world.owner, f"List for {shape}", *occasions)
    # A direct share, so visibility is constant across the matrix and the only
    # thing varying is which occasions the list is shared to. It widens neither
    # set: both are bounded by the occasion shares.
    db.add(ListShare(list_id=gift_list.id, user_id=world.claimer.id))
    db.flush()
    gift = _mkgift(db, gift_list, "Thing")

    detail = client.get(
        f"/lists/{gift_list.id}", headers=_auth(world.claimer)
    ).json()
    by_id = {o.id: ("X" if o.is_archived else "A") for o in occasions}
    assert sorted(by_id[o["id"]] for o in detail["claim_options"]) == sorted(
        expected_allowed
    )
    assert sorted(by_id[c["id"]] for c in detail["claim_candidates"]) == sorted(
        expected_suggested
    )

    resp = client.post(
        f"/lists/{gift_list.id}/gifts/{gift.id}/claim", headers=_auth(world.claimer)
    )
    if len(expected_suggested) >= 2:
        assert resp.status_code == 400
        assert resp.json()["detail"] == "ambiguous_occasion"
    else:
        assert resp.status_code == 201
        filed = resp.json()["occasion_id"]
        assert filed == (occasions[0].id if expected_suggested else None)


# ---------------------------------------------------------------------------
# The rules that predate filing still take precedence
# ---------------------------------------------------------------------------


def test_an_already_claimed_gift_is_409_even_when_ambiguous(client, db, world):
    smiths = _mkfamily(db, "The Smiths", world.owner, world.claimer)
    smiths_xmas = _mkoccasion(db, smiths, "Christmas 2026", world.owner)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=smiths_xmas.id))
    db.flush()
    _mkclaim(db, world.gift, world.claimer)

    assert _claim(client, world).status_code == 409


def test_the_owner_still_cannot_claim_their_own_gift(client, world):
    assert _claim(client, world, user=world.owner).status_code == 403


# ---------------------------------------------------------------------------
# PATCH /claims/{id}
# ---------------------------------------------------------------------------


def test_patch_moves_the_filing_within_allowed(client, db, world):
    grans = _mkoccasion(db, world.boones, "Gran's 80th", world.owner)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=grans.id))
    db.flush()
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)

    resp = client.patch(
        f"/claims/{claim.id}",
        headers=_auth(world.claimer),
        json={"occasion_id": grans.id},
    )
    assert resp.status_code == 200
    assert resp.json()["occasion_id"] == grans.id


def test_patch_can_clear_the_filing(client, db, world):
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)

    resp = client.patch(
        f"/claims/{claim.id}", headers=_auth(world.claimer), json={"occasion_id": None}
    )
    assert resp.status_code == 200
    assert resp.json()["occasion_id"] is None


def test_patch_to_an_occasion_outside_allowed_is_403(client, db, world):
    others = _mkfamily(db, "The Others", world.owner)
    foreign = _mkoccasion(db, others, "Not Yours", world.owner)
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)

    resp = client.patch(
        f"/claims/{claim.id}",
        headers=_auth(world.claimer),
        json={"occasion_id": foreign.id},
    )
    # No fallback here: on a PATCH the user is explicitly choosing, and silently
    # recording something else would be worse than refusing.
    assert resp.status_code == 403
    db.refresh(claim)
    assert claim.occasion_id == world.xmas.id


def test_patch_of_amount_only_leaves_the_filing_alone(client, db, world):
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)

    resp = client.patch(
        f"/claims/{claim.id}", headers=_auth(world.claimer), json={"amount_paid": "12.50"}
    )
    assert resp.status_code == 200
    assert resp.json()["amount_paid"] == "12.50"
    assert resp.json()["occasion_id"] == world.xmas.id


def test_patch_of_filing_only_leaves_the_amount_alone(client, db, world):
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)
    claim.amount_paid = Decimal("40.00")
    db.flush()

    resp = client.patch(
        f"/claims/{claim.id}", headers=_auth(world.claimer), json={"occasion_id": None}
    )
    assert resp.status_code == 200
    assert resp.json()["amount_paid"] == "40.00"


def test_the_list_owner_cannot_patch_a_claim_and_learns_nothing(client, db, world):
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)

    resp = client.patch(
        f"/claims/{claim.id}", headers=_auth(world.owner), json={"occasion_id": None}
    )
    assert resp.status_code == 403
    assert resp.json().get("detail") in (None, "Forbidden")


def test_a_claim_that_does_not_exist_answers_403_not_404(client, world):
    """Same answer as somebody else's claim, so probing ids reveals nothing."""
    resp = client.patch(
        "/claims/999999", headers=_auth(world.owner), json={"occasion_id": None}
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Filing is stored, never derived (§4)
# ---------------------------------------------------------------------------


def test_revoking_the_share_leaves_the_filing_untouched(client, db, world):
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)

    resp = client.delete(
        f"/lists/{world.list.id}/occasions/{world.xmas.id}?claims=keep",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    db.refresh(claim)
    assert claim.occasion_id == world.xmas.id


def test_revoking_the_share_leaves_the_filing_untouched_when_access_remains(
    client, db, world
):
    """The same rule on the revoke path that needs no `claims` disposition: the
    claimer keeps access by another route, so nothing is unclaimed and the
    filing has to survive on its own terms."""
    db.add(ListShare(list_id=world.list.id, user_id=world.claimer.id))
    db.flush()
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)

    resp = client.delete(
        f"/lists/{world.list.id}/occasions/{world.xmas.id}",
        headers=_auth(world.owner),
    )
    assert resp.status_code == 204
    db.refresh(claim)
    assert claim.occasion_id == world.xmas.id


def test_archiving_the_occasion_leaves_the_filing_untouched(client, db, world):
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)

    resp = client.put(
        f"/occasions/{world.xmas.id}",
        headers=_auth(world.owner),
        json={"is_archived": True},
    )
    assert resp.status_code == 200
    db.refresh(claim)
    assert claim.occasion_id == world.xmas.id


def test_leaving_the_family_leaves_a_surviving_filing_untouched(client, db, world):
    """Leaving deletes the share rows and may cascade the claim itself. Where the
    claim survives — here, because an accepted connection is another access path
    — its filing must survive with it."""
    db.add(
        Connection(
            requester_id=world.owner.id,
            addressee_id=world.claimer.id,
            status="accepted",
        )
    )
    db.flush()
    claim = _mkclaim(db, world.gift, world.claimer, world.xmas)

    resp = client.delete(
        f"/families/{world.boones.id}/members/{world.claimer.id}",
        headers=_auth(world.claimer),
    )
    assert resp.status_code == 204
    surviving = db.query(Claim).filter_by(gift_id=world.gift.id).one()
    assert surviving.occasion_id == world.xmas.id


# ---------------------------------------------------------------------------
# claim_candidates / claim_options on the list detail (§3.5)
# ---------------------------------------------------------------------------


def test_the_viewer_detail_carries_both_sets(client, db, world):
    world.xmas.is_archived = True
    grans = _mkoccasion(db, world.boones, "Gran's 80th", world.owner)
    db.add(ListOccasionShare(list_id=world.list.id, occasion_id=grans.id))
    db.flush()

    data = client.get(
        f"/lists/{world.list.id}", headers=_auth(world.claimer)
    ).json()

    assert [c["id"] for c in data["claim_candidates"]] == [grans.id]
    assert {o["id"] for o in data["claim_options"]} == {world.xmas.id, grans.id}
    entry = next(o for o in data["claim_options"] if o["id"] == world.xmas.id)
    # The picker needs a label, and two families routinely name an occasion the
    # same thing.
    assert entry["name"] == "Christmas 2026"
    assert entry["is_archived"] is True
    assert entry["family"] == {"id": world.boones.id, "name": "The Boones"}


def test_the_owner_detail_carries_neither_set(client, world):
    data = client.get(f"/lists/{world.list.id}", headers=_auth(world.owner)).json()
    # This is the class of field that produced the `claimed_count` leak.
    assert "claim_candidates" not in data
    assert "claim_options" not in data


def test_the_viewer_detail_hides_another_viewers_filing(client, db, world):
    """`occasion_id` is the claimer's private filing. It rides on the claim
    response, which only the claimer ever sees — never on the gift rows every
    viewer of the list reads."""
    other = _mkuser(db, "other@test.com", "Other")
    db.add(FamilyMember(family_id=world.boones.id, user_id=other.id, role="member"))
    db.flush()
    _mkclaim(db, world.gift, world.claimer, world.xmas)

    data = client.get(f"/lists/{world.list.id}", headers=_auth(other)).json()
    gift = data["gifts"][0]
    assert gift["claimed_by_id"] == world.claimer.id
    assert "occasion_id" not in gift


def test_the_owner_detail_still_carries_no_claim_state(client, db, world):
    _mkclaim(db, world.gift, world.claimer, world.xmas)

    data = client.get(f"/lists/{world.list.id}", headers=_auth(world.owner)).json()
    gift = data["gifts"][0]
    assert "occasion_id" not in gift
    assert "claimed_by_id" not in gift
