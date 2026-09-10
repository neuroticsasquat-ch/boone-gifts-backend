"""Family occasions — CRUD and the role gate (NEU-1263).

This is the first time role gates something a member can *see*, so the member
and organizer paths are covered explicitly on every endpoint: any member reads
and creates, only an organizer renames or archives.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sqlalchemy

from app.dependencies import create_access_token
from app.models.claim import Claim
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_occasion_share import ListOccasionShare
from app.models.occasion import Occasion
from app.models.user import User


@pytest.fixture
def family(db, member_user):
    """member_user (from conftest) organizes the family."""
    fam = Family(name="Boone Family", created_by_id=member_user.id)
    db.add(fam)
    db.flush()
    db.add(FamilyMember(family_id=fam.id, user_id=member_user.id, role="organizer"))
    db.flush()
    return fam


@pytest.fixture
def organizer_headers(member_headers):
    return member_headers


def _make_user(db, email: str, name: str) -> User:
    user = User(email=email, name=name, role="member", password_hash="x")
    user.set_password("x")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def plain_member(db, family):
    user = _make_user(db, "occasion_member@test.com", "Plain Member")
    db.add(FamilyMember(family_id=family.id, user_id=user.id, role="member"))
    db.flush()
    return user


@pytest.fixture
def plain_member_headers(plain_member):
    return {"Authorization": f"Bearer {create_access_token(plain_member)}"}


@pytest.fixture
def outsider(db):
    return _make_user(db, "occasion_outsider@test.com", "Outsider")


@pytest.fixture
def outsider_headers(outsider):
    return {"Authorization": f"Bearer {create_access_token(outsider)}"}


def _seed_occasion(
    db, family, creator, name="Christmas 2026", is_archived=False, created_at=None
):
    occasion = Occasion(
        family_id=family.id,
        name=name,
        created_by_id=creator.id,
        is_archived=is_archived,
    )
    # Set only when a test pins the clock: `created_at` is a server default, so
    # assigning None here would write a NULL rather than fall back to it.
    if created_at is not None:
        occasion.created_at = created_at
    db.add(occasion)
    db.flush()
    return occasion


# ---------------------------------------------------------------------------
# POST /families/{family_id}/occasions — any member
# ---------------------------------------------------------------------------


def test_organizer_creates_an_occasion(client, family, organizer_headers):
    response = client.post(
        f"/families/{family.id}/occasions",
        json={"name": "Christmas 2026"},
        headers=organizer_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Christmas 2026"
    assert body["family_id"] == family.id
    assert body["is_archived"] is False
    assert body["has_other_active"] is False


def test_a_plain_member_may_create_an_occasion(
    client, family, plain_member, plain_member_headers
):
    """Any member creates, so nobody waits on an absent organizer — a family
    with no active occasion cannot be shared to at all (ADR 0002)."""
    response = client.post(
        f"/families/{family.id}/occasions",
        json={"name": "Gran's 80th"},
        headers=plain_member_headers,
    )

    assert response.status_code == 201
    assert response.json()["created_by_id"] == plain_member.id


def test_a_second_active_occasion_is_created_and_flagged(
    client, db, family, member_user, organizer_headers
):
    """201, not a refusal — the warning is the client's to show."""
    _seed_occasion(db, family, member_user)

    response = client.post(
        f"/families/{family.id}/occasions",
        json={"name": "Gran's 80th"},
        headers=organizer_headers,
    )

    assert response.status_code == 201
    assert response.json()["has_other_active"] is True


def test_an_archived_occasion_does_not_count_as_other_active(
    client, db, family, member_user, organizer_headers
):
    _seed_occasion(db, family, member_user, name="Christmas 2025", is_archived=True)

    response = client.post(
        f"/families/{family.id}/occasions",
        json={"name": "Christmas 2026"},
        headers=organizer_headers,
    )

    assert response.json()["has_other_active"] is False


def test_an_outsider_cannot_create_an_occasion(client, family, outsider_headers):
    response = client.post(
        f"/families/{family.id}/occasions",
        json={"name": "Christmas 2026"},
        headers=outsider_headers,
    )

    assert response.status_code == 403


def test_creating_for_an_unknown_family_is_404(client, organizer_headers):
    response = client.post(
        "/families/99999/occasions",
        json={"name": "Christmas 2026"},
        headers=organizer_headers,
    )

    assert response.status_code == 404


def test_creating_requires_authentication(client, family):
    response = client.post(
        f"/families/{family.id}/occasions", json={"name": "Christmas 2026"}
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /families/{family_id}/occasions — any member
# ---------------------------------------------------------------------------


def test_listing_returns_active_occasions_by_default(
    client, db, family, member_user, organizer_headers
):
    _seed_occasion(db, family, member_user, name="Christmas 2026")
    _seed_occasion(db, family, member_user, name="Christmas 2025", is_archived=True)

    response = client.get(
        f"/families/{family.id}/occasions", headers=organizer_headers
    )

    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["Christmas 2026"]


def test_listing_can_ask_for_the_archived_ones(
    client, db, family, member_user, organizer_headers
):
    _seed_occasion(db, family, member_user, name="Christmas 2026")
    _seed_occasion(db, family, member_user, name="Christmas 2025", is_archived=True)

    response = client.get(
        f"/families/{family.id}/occasions?archived=true", headers=organizer_headers
    )

    assert [row["name"] for row in response.json()] == ["Christmas 2025"]


def test_a_plain_member_may_list_occasions(
    client, db, family, member_user, plain_member, plain_member_headers
):
    _seed_occasion(db, family, member_user)

    response = client.get(
        f"/families/{family.id}/occasions", headers=plain_member_headers
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_listing_excludes_another_familys_occasions(
    client, db, family, member_user, organizer_headers
):
    other = Family(name="Extended Family", created_by_id=member_user.id)
    db.add(other)
    db.flush()
    db.add(
        FamilyMember(family_id=other.id, user_id=member_user.id, role="organizer")
    )
    db.flush()
    _seed_occasion(db, family, member_user, name="Boone Christmas")
    _seed_occasion(db, other, member_user, name="Extended Christmas")

    response = client.get(
        f"/families/{family.id}/occasions", headers=organizer_headers
    )

    assert [row["name"] for row in response.json()] == ["Boone Christmas"]


def test_an_outsider_cannot_list_occasions(client, family, outsider_headers):
    response = client.get(
        f"/families/{family.id}/occasions", headers=outsider_headers
    )

    assert response.status_code == 403


def test_listing_an_unknown_familys_occasions_is_404(client, organizer_headers):
    response = client.get("/families/99999/occasions", headers=organizer_headers)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /occasions/{id} — any member of the owning family
# ---------------------------------------------------------------------------


def test_a_member_reads_an_occasion(
    client, db, family, member_user, plain_member, plain_member_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.get(f"/occasions/{occasion.id}", headers=plain_member_headers)

    assert response.status_code == 200
    assert response.json()["name"] == "Christmas 2026"


def test_an_outsider_cannot_read_an_occasion(
    client, db, family, member_user, outsider_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.get(f"/occasions/{occasion.id}", headers=outsider_headers)

    assert response.status_code == 403


def test_reading_an_unknown_occasion_is_404(client, organizer_headers):
    response = client.get("/occasions/99999", headers=organizer_headers)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PUT /occasions/{id} — organizer only
# ---------------------------------------------------------------------------


def test_an_organizer_renames_an_occasion(
    client, db, family, member_user, organizer_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.put(
        f"/occasions/{occasion.id}",
        json={"name": "Christmas 2027"},
        headers=organizer_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Christmas 2027"


def test_an_organizer_archives_an_occasion(
    client, db, family, member_user, organizer_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.put(
        f"/occasions/{occasion.id}",
        json={"is_archived": True},
        headers=organizer_headers,
    )

    assert response.status_code == 200
    assert response.json()["is_archived"] is True


def test_an_organizer_unarchives_an_occasion(
    client, db, family, member_user, organizer_headers
):
    occasion = _seed_occasion(db, family, member_user, is_archived=True)

    response = client.put(
        f"/occasions/{occasion.id}",
        json={"is_archived": False},
        headers=organizer_headers,
    )

    assert response.json()["is_archived"] is False


def test_a_partial_update_leaves_the_other_field_alone(
    client, db, family, member_user, organizer_headers
):
    occasion = _seed_occasion(db, family, member_user, is_archived=True)

    response = client.put(
        f"/occasions/{occasion.id}",
        json={"name": "Christmas 2025"},
        headers=organizer_headers,
    )

    body = response.json()
    assert body["name"] == "Christmas 2025"
    assert body["is_archived"] is True


def test_a_plain_member_cannot_rename_an_occasion(
    client, db, family, member_user, plain_member, plain_member_headers
):
    """The role gate that makes this ticket different: a member can see the
    occasion and still not rename it."""
    occasion = _seed_occasion(db, family, member_user)

    response = client.put(
        f"/occasions/{occasion.id}",
        json={"name": "Renamed by a member"},
        headers=plain_member_headers,
    )

    assert response.status_code == 403
    db.refresh(occasion)
    assert occasion.name == "Christmas 2026"


def test_a_plain_member_cannot_archive_an_occasion(
    client, db, family, member_user, plain_member, plain_member_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.put(
        f"/occasions/{occasion.id}",
        json={"is_archived": True},
        headers=plain_member_headers,
    )

    assert response.status_code == 403
    db.refresh(occasion)
    assert occasion.is_archived is False


def test_an_outsider_cannot_update_an_occasion(
    client, db, family, member_user, outsider_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.put(
        f"/occasions/{occasion.id}",
        json={"name": "Renamed by an outsider"},
        headers=outsider_headers,
    )

    assert response.status_code == 403


def test_updating_an_unknown_occasion_is_404(client, organizer_headers):
    response = client.put(
        "/occasions/99999", json={"name": "Nowhere"}, headers=organizer_headers
    )

    assert response.status_code == 404


def test_an_explicit_null_name_is_refused(
    client, db, family, member_user, organizer_headers
):
    """`exclude_unset` keeps an explicit null, which would otherwise write NULL
    into a NOT NULL column and 500."""
    occasion = _seed_occasion(db, family, member_user)

    response = client.put(
        f"/occasions/{occasion.id}", json={"name": None}, headers=organizer_headers
    )

    assert response.status_code == 422
    db.refresh(occasion)
    assert occasion.name == "Christmas 2026"


def test_an_explicit_null_is_archived_is_refused(
    client, db, family, member_user, organizer_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.put(
        f"/occasions/{occasion.id}",
        json={"is_archived": None},
        headers=organizer_headers,
    )

    assert response.status_code == 422
    db.refresh(occasion)
    assert occasion.is_archived is False


def test_an_empty_update_is_a_no_op(
    client, db, family, member_user, organizer_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.put(
        f"/occasions/{occasion.id}", json={}, headers=organizer_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Christmas 2026"


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/families/{family_id}/occasions"),
        ("get", "/occasions/{occasion_id}"),
        ("put", "/occasions/{occasion_id}"),
    ],
)
def test_every_endpoint_requires_authentication(
    client, db, family, member_user, method, path
):
    occasion = _seed_occasion(db, family, member_user)
    url = path.format(family_id=family.id, occasion_id=occasion.id)

    kwargs = {"json": {"name": "Nope"}} if method == "put" else {}
    response = getattr(client, method)(url, **kwargs)

    assert response.status_code == 401


def test_deleting_a_family_that_has_occasions_succeeds(
    client, db, family, member_user, organizer_headers
):
    """`delete_family` clears everything pointing at the family so the delete
    itself can succeed; occasions are now one of those things."""
    _seed_occasion(db, family, member_user)

    response = client.delete(f"/families/{family.id}", headers=organizer_headers)

    assert response.status_code == 204
    assert (
        db.execute(
            sqlalchemy.select(Occasion).where(Occasion.family_id == family.id)
        ).first()
        is None
    )


# ---------------------------------------------------------------------------
# GET /occasions/{id}/lists  (NEU-1265)
# ---------------------------------------------------------------------------


def _seed_list(db, owner, name):
    gift_list = GiftList(name=name, owner_id=owner.id)
    db.add(gift_list)
    db.flush()
    return gift_list


def test_lists_returns_the_lists_shared_to_the_occasion(
    client, db, family, member_user, plain_member, plain_member_headers
):
    occasion = _seed_occasion(db, family, member_user)
    shared = _seed_list(db, member_user, "Organizer's List")
    unshared = _seed_list(db, member_user, "Kept Private")
    db.add(ListOccasionShare(list_id=shared.id, occasion_id=occasion.id))
    db.flush()

    response = client.get(
        f"/occasions/{occasion.id}/lists", headers=plain_member_headers
    )

    assert response.status_code == 200
    names = {row["name"] for row in response.json()}
    assert names == {"Organizer's List"}
    assert unshared.name not in names


def test_lists_includes_the_callers_own_list(
    client, db, family, member_user, member_headers
):
    """The viewer owns it, so `can_view_list` passes and it belongs on the page
    like any other list shared to the occasion."""
    occasion = _seed_occasion(db, family, member_user)
    own = _seed_list(db, member_user, "My Own List")
    db.add(ListOccasionShare(list_id=own.id, occasion_id=occasion.id))
    db.flush()

    response = client.get(f"/occasions/{occasion.id}/lists", headers=member_headers)

    assert {row["name"] for row in response.json()} == {"My Own List"}


def test_lists_serves_a_list_owned_by_a_co_member(
    client, db, family, member_user, plain_member, plain_member_headers
):
    """Every row on the page passes `can_view_list` by construction: the share
    puts the list on an occasion of a family the caller belongs to, which is the
    predicate's third arm. The filter is the single-predicate discipline, not a
    second gate."""
    occasion = _seed_occasion(db, family, member_user)
    co_member = _make_user(db, "occasion_cousin@test.com", "Cousin")
    db.add(FamilyMember(family_id=family.id, user_id=co_member.id, role="member"))
    cousins_list = _seed_list(db, co_member, "Cousin's List")
    db.add(ListOccasionShare(list_id=cousins_list.id, occasion_id=occasion.id))
    db.flush()

    response = client.get(
        f"/occasions/{occasion.id}/lists", headers=plain_member_headers
    )

    assert {row["name"] for row in response.json()} == {"Cousin's List"}


def test_lists_still_served_for_an_archived_occasion(
    client, db, family, member_user, plain_member, plain_member_headers
):
    """Archiving blocks new shares, and only that — its lists stay viewable."""
    occasion = _seed_occasion(db, family, member_user, is_archived=True)
    shared = _seed_list(db, member_user, "Organizer's List")
    db.add(ListOccasionShare(list_id=shared.id, occasion_id=occasion.id))
    db.flush()

    response = client.get(
        f"/occasions/{occasion.id}/lists", headers=plain_member_headers
    )

    assert {row["name"] for row in response.json()} == {"Organizer's List"}


def test_lists_forbidden_for_a_non_member(client, db, family, member_user, outsider_headers):
    occasion = _seed_occasion(db, family, member_user)

    response = client.get(
        f"/occasions/{occasion.id}/lists", headers=outsider_headers
    )

    assert response.status_code == 403


def test_lists_not_found_for_an_occasion_that_does_not_exist(client, member_headers):
    response = client.get("/occasions/999999/lists", headers=member_headers)

    assert response.status_code == 404


def test_lists_requires_authentication(client, db, family, member_user):
    occasion = _seed_occasion(db, family, member_user)

    assert client.get(f"/occasions/{occasion.id}/lists").status_code == 401


# ---------------------------------------------------------------------------
# GET /occasions/{id}/shopping — the caller's own claims, and nobody else's
# ---------------------------------------------------------------------------


def _seed_claim(
    db,
    gift_list,
    claimer,
    name,
    occasion=None,
    purchased_at=None,
    amount_paid=None,
    price=None,
    claimed_at=None,
):
    """A gift with a claim standing on it — two rows since ADR 0003."""
    gift = Gift(list_id=gift_list.id, name=name, price=price)
    db.add(gift)
    db.flush()
    claim = Claim(
        gift_id=gift.id,
        user_id=claimer.id,
        occasion_id=occasion.id if occasion is not None else None,
        claimed_at=claimed_at or datetime.now(timezone.utc),
        purchased_at=purchased_at,
        amount_paid=amount_paid,
    )
    db.add(claim)
    db.flush()
    return claim


def test_shopping_never_returns_another_members_claims(
    client, db, family, member_user, plain_member, plain_member_headers
):
    """`CONTEXT.md` invariant 1, at the one endpoint most tempted to break it.

    Both claims are filed under the same occasion, on the same list, by two
    members of the same family — everything matches except the claimer.
    """
    occasion = _seed_occasion(db, family, member_user)
    gift_list = _seed_list(db, member_user, "Gran's List")
    _seed_claim(db, gift_list, plain_member, "Mine", occasion=occasion)
    _seed_claim(db, gift_list, member_user, "Not mine", occasion=occasion)

    response = client.get(
        f"/occasions/{occasion.id}/shopping", headers=plain_member_headers
    )

    assert response.status_code == 200
    assert [row["name"] for row in response.json()["items"]] == ["Mine"]


def test_shopping_returns_only_claims_filed_under_this_occasion(
    client, db, family, member_user, plain_member, plain_member_headers
):
    occasion = _seed_occasion(db, family, member_user)
    other = _seed_occasion(db, family, member_user, name="Gran's 80th")
    gift_list = _seed_list(db, member_user, "Gran's List")
    _seed_claim(db, gift_list, plain_member, "Filed here", occasion=occasion)
    _seed_claim(db, gift_list, plain_member, "Filed elsewhere", occasion=other)
    _seed_claim(db, gift_list, plain_member, "Filed nowhere")

    response = client.get(
        f"/occasions/{occasion.id}/shopping", headers=plain_member_headers
    )

    assert [row["name"] for row in response.json()["items"]] == ["Filed here"]


def test_shopping_carries_the_whole_line(
    client, db, family, member_user, plain_member, plain_member_headers
):
    """Gift, the owner's asking price, the list it came from, and the
    claimer's own purchase state — the shopping tab renders all of it."""
    occasion = _seed_occasion(db, family, member_user)
    gift_list = _seed_list(db, member_user, "Gran's List")
    claim = _seed_claim(
        db,
        gift_list,
        plain_member,
        "Cast iron skillet",
        occasion=occasion,
        purchased_at=datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc),
        amount_paid=Decimal("31.50"),
        price=Decimal("39.00"),
    )
    gift = db.get(Gift, claim.gift_id)
    gift.description = "The 12-inch one"
    gift.url = "https://example.com/skillet"
    db.flush()

    row = client.get(
        f"/occasions/{occasion.id}/shopping", headers=plain_member_headers
    ).json()["items"][0]

    assert row["claim_id"] == claim.id
    assert row["gift_id"] == gift.id
    assert row["name"] == "Cast iron skillet"
    assert row["description"] == "The 12-inch one"
    assert row["url"] == "https://example.com/skillet"
    # The owner's asking price and the claimer's spend are separate facts, and
    # neither is ever seeded from the other.
    assert row["price"] == "39.00"
    assert row["amount_paid"] == "31.50"
    assert row["list_id"] == gift_list.id
    assert row["list_name"] == "Gran's List"
    assert row["purchased_at"] is not None


def test_shopping_groups_by_list_in_a_stable_order(
    client, db, family, member_user, plain_member, plain_member_headers
):
    occasion = _seed_occasion(db, family, member_user)
    first = _seed_list(db, member_user, "Gran's List")
    second = _seed_list(db, member_user, "Jane's Wishlist")
    _seed_claim(db, first, plain_member, "A1", occasion=occasion)
    _seed_claim(db, second, plain_member, "B1", occasion=occasion)
    _seed_claim(db, first, plain_member, "A2", occasion=occasion)

    names = [
        row["name"]
        for row in client.get(
            f"/occasions/{occasion.id}/shopping", headers=plain_member_headers
        ).json()["items"]
    ]

    assert names == ["A1", "A2", "B1"]


def test_shopping_still_served_for_an_archived_occasion(
    client, db, family, member_user, plain_member, plain_member_headers
):
    """The January shopper is still buying against December's occasion."""
    occasion = _seed_occasion(db, family, member_user, is_archived=True)
    gift_list = _seed_list(db, member_user, "Gran's List")
    _seed_claim(db, gift_list, plain_member, "Bought in January", occasion=occasion)

    response = client.get(
        f"/occasions/{occasion.id}/shopping", headers=plain_member_headers
    )

    assert response.status_code == 200
    assert [row["name"] for row in response.json()["items"]] == ["Bought in January"]


def test_shopping_survives_the_share_being_revoked(
    client, db, family, member_user, plain_member, plain_member_headers
):
    """Filing is stored, not derived — a claim that outlived its share still
    belongs to the budget it was filed under."""
    occasion = _seed_occasion(db, family, member_user)
    gift_list = _seed_list(db, member_user, "Gran's List")
    share = ListOccasionShare(list_id=gift_list.id, occasion_id=occasion.id)
    db.add(share)
    db.flush()
    _seed_claim(db, gift_list, plain_member, "Still mine", occasion=occasion)
    db.delete(share)
    db.flush()

    response = client.get(
        f"/occasions/{occasion.id}/shopping", headers=plain_member_headers
    )

    assert [row["name"] for row in response.json()["items"]] == ["Still mine"]


def test_shopping_is_empty_when_nothing_is_filed(
    client, db, family, member_user, plain_member_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.get(
        f"/occasions/{occasion.id}/shopping", headers=plain_member_headers
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_shopping_forbidden_for_a_non_member(
    client, db, family, member_user, outsider_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.get(
        f"/occasions/{occasion.id}/shopping", headers=outsider_headers
    )

    assert response.status_code == 403


def test_shopping_not_found_for_an_occasion_that_does_not_exist(
    client, member_headers
):
    response = client.get("/occasions/999999/shopping", headers=member_headers)

    assert response.status_code == 404


def test_shopping_requires_authentication(client, db, family, member_user):
    occasion = _seed_occasion(db, family, member_user)

    assert client.get(f"/occasions/{occasion.id}/shopping").status_code == 401


# ---------------------------------------------------------------------------
# GET /occasions — the index the landing strip reads (NEU-1292)
#
# The clock these rows sort on is per-viewer and never reads another user's
# claim (ADR 0005). The first three tests below are that rule; everything after
# them is the rest of the contract.
# ---------------------------------------------------------------------------

# Far enough from anything the fixtures write that "did the clock move?" cannot
# turn on which side of a second boundary the test happened to land.
LATER = datetime(2030, 1, 1, 12, 0, 0)
LATER_STILL = LATER + timedelta(days=365)


def _index(client, headers, **params):
    response = client.get("/occasions", headers=headers, params=params)
    assert response.status_code == 200
    return response.json()


def _row(payload, occasion):
    return next(row for row in payload if row["id"] == occasion.id)


@pytest.fixture
def co_member(db, family):
    """A second member of the same family — the other user in every leak test."""
    user = _make_user(db, "occasion_co_member@test.com", "Co Member")
    db.add(FamilyMember(family_id=family.id, user_id=user.id, role="member"))
    db.flush()
    return user


def test_another_users_claim_on_my_own_list_moves_nothing(
    client, db, family, member_user, member_headers, co_member
):
    """**The most important test in the project** (spec §13).

    The caller owns the only list on this occasion. When somebody else claims
    and buys from it, every number the caller reads must be byte-identical to
    what it was before — the counts *and* the clock. `CONTEXT.md` invariant 1
    is not only about fields: the strip sorts on `last_activity_at`, so an
    occasion that climbs the moment a gift is taken tells its owner that
    someone is buying them a present, and roughly when.
    """
    occasion = _seed_occasion(db, family, member_user)
    my_list = _seed_list(db, member_user, "My Own Wishlist")
    db.add(ListOccasionShare(list_id=my_list.id, occasion_id=occasion.id))
    db.flush()

    before = _row(_index(client, member_headers), occasion)

    _seed_claim(
        db,
        my_list,
        co_member,
        "Wool socks",
        occasion=occasion,
        claimed_at=LATER,
        purchased_at=LATER_STILL,
        amount_paid=Decimal("20.00"),
    )

    after = _row(_index(client, member_headers), occasion)

    assert after == before
    assert after["my_claimed_count"] == 0
    assert after["my_bought_count"] == 0
    assert after["last_activity_at"] < LATER.isoformat()


def test_another_users_claim_on_a_list_i_do_not_own_moves_nothing_either(
    client, db, family, member_user, member_headers, co_member
):
    """The same guard where the leak would be less alarming but no less real:
    the clock is the viewer's own activity, not the occasion's."""
    occasion = _seed_occasion(db, family, member_user)
    their_list = _seed_list(db, co_member, "Co Member's Wishlist")
    db.add(ListOccasionShare(list_id=their_list.id, occasion_id=occasion.id))
    db.flush()

    before = _row(_index(client, member_headers), occasion)

    _seed_claim(
        db,
        their_list,
        co_member,
        "Something for themselves",
        occasion=occasion,
        claimed_at=LATER,
        purchased_at=LATER_STILL,
    )

    assert _row(_index(client, member_headers), occasion) == before


def test_my_own_claim_and_purchase_move_all_three(
    client, db, family, member_user, member_headers, co_member
):
    """The other half of the rule: hiding another user's shopping must not hide
    the caller's own, or the clock is useless for the thing it was built for."""
    occasion = _seed_occasion(db, family, member_user)
    their_list = _seed_list(db, co_member, "Co Member's Wishlist")
    db.add(ListOccasionShare(list_id=their_list.id, occasion_id=occasion.id))
    db.flush()

    before = _row(_index(client, member_headers), occasion)
    assert before["my_claimed_count"] == 0
    assert before["my_bought_count"] == 0

    _seed_claim(
        db,
        their_list,
        member_user,
        "A gift for them",
        occasion=occasion,
        claimed_at=LATER,
    )

    claimed = _row(_index(client, member_headers), occasion)
    assert claimed["my_claimed_count"] == 1
    assert claimed["my_bought_count"] == 0
    assert claimed["last_activity_at"] == LATER.isoformat()

    _seed_claim(
        db,
        their_list,
        member_user,
        "A second gift",
        occasion=occasion,
        claimed_at=LATER,
        purchased_at=LATER_STILL,
    )

    bought = _row(_index(client, member_headers), occasion)
    assert bought["my_claimed_count"] == 2
    assert bought["my_bought_count"] == 1
    assert bought["last_activity_at"] == LATER_STILL.isoformat()


def test_the_index_spans_every_family_and_keeps_the_empty_occasions(
    client, db, family, member_user, member_headers
):
    """One request, every family — including the occasions with no lists at
    all, which §5.1 says are the ones most likely to need action."""
    second = Family(name="Extended Family", created_by_id=member_user.id)
    db.add(second)
    db.flush()
    db.add(
        FamilyMember(family_id=second.id, user_id=member_user.id, role="member")
    )
    db.flush()

    boone = _seed_occasion(db, family, member_user, name="Boone Christmas")
    extended = _seed_occasion(db, second, member_user, name="Extended Christmas")
    shared = _seed_list(db, member_user, "A List")
    db.add(ListOccasionShare(list_id=shared.id, occasion_id=boone.id))
    db.flush()

    payload = _index(client, member_headers)

    assert {row["id"] for row in payload} == {boone.id, extended.id}
    assert _row(payload, boone)["family_name"] == "Boone Family"
    assert _row(payload, boone)["list_count"] == 1
    assert _row(payload, extended)["family_name"] == "Extended Family"
    assert _row(payload, extended)["list_count"] == 0


def test_an_occasion_nothing_has_happened_to_reads_its_creation(
    client, db, family, member_user, member_headers
):
    """The floor, asserted as a value rather than as truthiness: SQLite's
    scalar `max()` returns NULL if any argument is NULL, so the uncoalesced
    spelling regresses to `null` here — on the commonest row of all."""
    created = datetime(2026, 3, 1, 9, 30, 0)
    occasion = _seed_occasion(db, family, member_user, created_at=created)

    row = _row(_index(client, member_headers), occasion)

    assert row["last_activity_at"] == created.isoformat()


def test_a_share_into_the_occasion_moves_the_clock(
    client, db, family, member_user, member_headers, co_member
):
    """A share is the one activity by another person the clock may read: the
    list it carries is already visible to every member, so it announces
    nothing they could not see by looking."""
    occasion = _seed_occasion(
        db, family, member_user, created_at=datetime(2026, 3, 1, 9, 30, 0)
    )
    their_list = _seed_list(db, co_member, "Co Member's Wishlist")
    share = ListOccasionShare(list_id=their_list.id, occasion_id=occasion.id)
    share.created_at = LATER
    db.add(share)
    db.flush()

    row = _row(_index(client, member_headers), occasion)

    assert row["last_activity_at"] == LATER.isoformat()


def test_rows_are_ordered_by_the_clock_then_by_id(
    client, db, family, member_user, member_headers
):
    occasion = _seed_occasion  # local alias keeps the seeding lines readable
    quiet = occasion(db, family, member_user, created_at=datetime(2026, 1, 1))
    busy = occasion(db, family, member_user, created_at=datetime(2026, 6, 1))
    middling = occasion(db, family, member_user, created_at=datetime(2026, 3, 1))

    ids = [row["id"] for row in _index(client, member_headers)]

    assert ids == [busy.id, middling.id, quiet.id]


def test_occasions_that_tie_come_back_by_descending_id_stably(
    client, db, family, member_user, member_headers
):
    """Two occasions created in one transaction share `created_at` to the
    second, so the tiebreak is what stops "the first four" being whatever the
    query plan yields — and what stops two members seeing different strips."""
    tie = datetime(2026, 4, 1, 12, 0, 0)
    first = _seed_occasion(db, family, member_user, name="One", created_at=tie)
    second = _seed_occasion(db, family, member_user, name="Two", created_at=tie)
    third = _seed_occasion(db, family, member_user, name="Three", created_at=tie)

    expected = [third.id, second.id, first.id]
    assert [row["id"] for row in _index(client, member_headers)] == expected
    assert [row["id"] for row in _index(client, member_headers)] == expected


def test_archived_is_an_exact_match_in_all_three_forms(
    client, db, family, member_user, member_headers
):
    """`archived=true` is the archived ones *only*, never a union — one
    parameter name meaning one thing across both occasion index endpoints."""
    active = _seed_occasion(db, family, member_user, name="Active")
    archived = _seed_occasion(
        db, family, member_user, name="Archived", is_archived=True
    )

    assert [row["id"] for row in _index(client, member_headers)] == [active.id]
    assert [
        row["id"] for row in _index(client, member_headers, archived="false")
    ] == [active.id]
    assert [
        row["id"] for row in _index(client, member_headers, archived="true")
    ] == [archived.id]


def test_a_caller_in_no_families_gets_an_empty_list(client, outsider_headers):
    """Not a 404: an occasion the caller cannot see is not a row this query
    filters out, it is a row it never produces."""
    assert _index(client, outsider_headers) == []


def test_list_count_matches_the_lists_endpoint(
    client, db, family, member_user, co_member, plain_member, plain_member_headers
):
    """Decision 5's guard. `list_count` is a raw aggregate over the share rows
    rather than a per-list `can_view_list` pass — the two are provably equal
    here, and this is what fails loudly if that stops being true."""
    occasion = _seed_occasion(db, family, member_user)
    for owner, name in (
        (member_user, "Organizer's List"),
        (co_member, "Co Member's List"),
        (plain_member, "My Own List"),
    ):
        gift_list = _seed_list(db, owner, name)
        db.add(ListOccasionShare(list_id=gift_list.id, occasion_id=occasion.id))
    db.flush()

    from_index = _row(_index(client, plain_member_headers), occasion)["list_count"]
    from_endpoint = client.get(
        f"/occasions/{occasion.id}/lists", headers=plain_member_headers
    )

    assert from_endpoint.status_code == 200
    assert from_index == len(from_endpoint.json()) == 3


def test_several_lists_and_several_claims_do_not_multiply(
    client, db, family, member_user, member_headers, co_member
):
    """Decision 4a: two `LEFT JOIN`s into one grouped query fan the rows out
    and `list_count` comes back as the product."""
    occasion = _seed_occasion(db, family, member_user)
    for index in range(3):
        gift_list = _seed_list(db, co_member, f"List {index}")
        db.add(ListOccasionShare(list_id=gift_list.id, occasion_id=occasion.id))
        db.flush()
        _seed_claim(db, gift_list, member_user, f"Gift {index}", occasion=occasion)

    row = _row(_index(client, member_headers), occasion)

    assert row["list_count"] == 3
    assert row["my_claimed_count"] == 3


def test_a_claim_survives_its_list_being_unshared(
    client, db, family, member_user, member_headers, co_member
):
    """Decision 1's accepted consequence: filing is stored and never
    re-derived, so an occasion with no lists left can still report claims."""
    occasion = _seed_occasion(db, family, member_user)
    their_list = _seed_list(db, co_member, "Co Member's Wishlist")
    share = ListOccasionShare(list_id=their_list.id, occasion_id=occasion.id)
    db.add(share)
    db.flush()
    _seed_claim(db, their_list, member_user, "A gift", occasion=occasion)
    db.delete(share)
    db.flush()

    row = _row(_index(client, member_headers), occasion)

    assert row["list_count"] == 0
    assert row["my_claimed_count"] == 1


def test_the_index_excludes_a_family_the_caller_does_not_belong_to(
    client, db, family, member_user, member_headers, co_member
):
    """Membership is what scopes the query, so a family the caller is not in
    contributes no row at all — not a row with blanked counts."""
    second = Family(name="Someone Else's Family", created_by_id=co_member.id)
    db.add(second)
    db.flush()
    db.add(FamilyMember(family_id=second.id, user_id=co_member.id, role="organizer"))
    theirs = _seed_occasion(db, second, co_member, name="Not Mine")
    db.flush()

    assert theirs.id not in {row["id"] for row in _index(client, member_headers)}


def test_the_index_requires_authentication(client):
    assert client.get("/occasions").status_code == 401
