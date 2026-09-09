"""Family occasions — CRUD and the role gate (NEU-1263).

This is the first time role gates something a member can *see*, so the member
and organizer paths are covered explicitly on every endpoint: any member reads
and creates, only an organizer renames or archives.
"""
from datetime import datetime, timezone
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


def _seed_occasion(db, family, creator, name="Christmas 2026", is_archived=False):
    occasion = Occasion(
        family_id=family.id,
        name=name,
        created_by_id=creator.id,
        is_archived=is_archived,
    )
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
):
    """A gift with a claim standing on it — two rows since ADR 0003."""
    gift = Gift(list_id=gift_list.id, name=name, price=price)
    db.add(gift)
    db.flush()
    claim = Claim(
        gift_id=gift.id,
        user_id=claimer.id,
        occasion_id=occasion.id if occasion is not None else None,
        claimed_at=datetime.now(timezone.utc),
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
    assert [row["name"] for row in response.json()] == ["Mine"]


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

    assert [row["name"] for row in response.json()] == ["Filed here"]


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
    ).json()[0]

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
        ).json()
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
    assert [row["name"] for row in response.json()] == ["Bought in January"]


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

    assert [row["name"] for row in response.json()] == ["Still mine"]


def test_shopping_is_empty_when_nothing_is_filed(
    client, db, family, member_user, plain_member_headers
):
    occasion = _seed_occasion(db, family, member_user)

    response = client.get(
        f"/occasions/{occasion.id}/shopping", headers=plain_member_headers
    )

    assert response.status_code == 200
    assert response.json() == []


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
