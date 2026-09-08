"""Family occasions — CRUD and the role gate (NEU-1263).

This is the first time role gates something a member can *see*, so the member
and organizer paths are covered explicitly on every endpoint: any member reads
and creates, only an organizer renames or archives.
"""
import pytest
import sqlalchemy

from app.dependencies import create_access_token
from app.models.family import Family
from app.models.family_member import FamilyMember
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
