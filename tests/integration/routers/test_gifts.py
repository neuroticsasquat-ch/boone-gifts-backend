import threading

from app.models.gift import Gift


def test_create_gift(client, member_headers, sample_list):
    response = client.post(
        f"/lists/{sample_list.id}/gifts",
        headers=member_headers,
        json={
            "name": "Book",
            "description": "A great read",
            "url": "https://example.com/book",
            "price": "19.99",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Book"
    assert data["description"] == "A great read"
    assert data["url"] == "https://example.com/book"
    assert data["price"] == "19.99"


def test_create_gift_minimal(client, member_headers, sample_list):
    response = client.post(
        f"/lists/{sample_list.id}/gifts",
        headers=member_headers,
        json={"name": "Surprise"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["description"] is None
    assert data["url"] is None
    assert data["price"] is None


def test_create_gift_not_owner(client, admin_headers, shared_list):
    response = client.post(
        f"/lists/{shared_list.id}/gifts",
        headers=admin_headers,
        json={"name": "Nope"},
    )
    assert response.status_code == 403


def test_update_gift(client, member_headers, sample_list, db):
    gift = Gift(list_id=sample_list.id, name="Old Name")
    db.add(gift)
    db.flush()

    response = client.put(
        f"/lists/{sample_list.id}/gifts/{gift.id}",
        headers=member_headers,
        json={"name": "New Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_update_gift_not_owner(client, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Protected")
    db.add(gift)
    db.flush()

    response = client.put(
        f"/lists/{shared_list.id}/gifts/{gift.id}",
        headers=admin_headers,
        json={"name": "Hacked"},
    )
    assert response.status_code == 403


def test_update_gift_not_found(client, member_headers, sample_list):
    response = client.put(
        f"/lists/{sample_list.id}/gifts/99999",
        headers=member_headers,
        json={"name": "Ghost"},
    )
    assert response.status_code == 404


def test_delete_gift(client, member_headers, sample_list, db):
    gift = Gift(list_id=sample_list.id, name="Delete Me")
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/lists/{sample_list.id}/gifts/{gift.id}",
        headers=member_headers,
    )
    assert response.status_code == 204


def test_delete_gift_claimed(client, member_headers, admin_user, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Claimed Gift")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/lists/{shared_list.id}/gifts/{gift.id}",
        headers=member_headers,
    )
    assert response.status_code == 409


def test_delete_gift_not_owner(client, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Protected")
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/lists/{shared_list.id}/gifts/{gift.id}",
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_claim_gift(client, admin_user, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Claimable")
    db.add(gift)
    db.flush()

    response = client.post(
        f"/lists/{shared_list.id}/gifts/{gift.id}/claim",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["claimed_by_id"] == admin_user.id
    assert data["claimed_at"] is not None


def test_claim_gift_already_claimed(client, admin_user, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Taken")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.post(
        f"/lists/{shared_list.id}/gifts/{gift.id}/claim",
        headers=admin_headers,
    )
    assert response.status_code == 409


def test_claim_gift_as_owner(client, member_headers, sample_list, db):
    gift = Gift(list_id=sample_list.id, name="Own Gift")
    db.add(gift)
    db.flush()

    response = client.post(
        f"/lists/{sample_list.id}/gifts/{gift.id}/claim",
        headers=member_headers,
    )
    assert response.status_code == 403


def test_unclaim_gift(client, admin_user, admin_headers, shared_list, db):
    gift = Gift(list_id=shared_list.id, name="Unclaim Me")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/lists/{shared_list.id}/gifts/{gift.id}/claim",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["claimed_by_id"] is None
    assert data["claimed_at"] is None


def test_unclaim_gift_by_other_user(
    client, member_user, admin_user, member_headers, shared_list, db
):
    gift = Gift(list_id=shared_list.id, name="Not Yours")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/lists/{shared_list.id}/gifts/{gift.id}/claim",
        headers=member_headers,
    )
    assert response.status_code == 403


def test_get_list_hides_claims_from_owner(
    client, member_headers, admin_user, shared_list, db
):
    gift = Gift(list_id=shared_list.id, name="Secret Claim")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.get(f"/lists/{shared_list.id}", headers=member_headers)
    assert response.status_code == 200
    gift_data = response.json()["gifts"][0]
    assert "claimed_by_id" not in gift_data
    assert "claimed_at" not in gift_data


def test_get_list_shows_claims_to_shared_user(
    client, admin_user, admin_headers, shared_list, db
):
    gift = Gift(list_id=shared_list.id, name="Visible Claim")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.get(f"/lists/{shared_list.id}", headers=admin_headers)
    assert response.status_code == 200
    gift_data = response.json()["gifts"][0]
    assert gift_data["claimed_by_id"] == admin_user.id


def test_concurrent_claims_exactly_one_wins():
    """
    Verify that the atomic UPDATE WHERE claim prevents double-claiming under
    concurrent load. Each thread gets its own DB session (no shared-session
    override) so SQLite sees two truly independent writers.
    """
    from app.models.gift_list import GiftList
    from app.models.list_share import ListShare
    from app.models.connection import Connection
    from app.models.user import User
    from app.database import SessionLocal, engine as _engine
    from app.dependencies import create_access_token
    from app.main import app
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    def _cleanup(conn):
        """Remove all committed race-test data using raw SQL (FK-safe order)."""
        conn.execute(text(
            "DELETE FROM gifts WHERE list_id IN "
            "(SELECT id FROM lists WHERE owner_id IN "
            "(SELECT id FROM users WHERE email LIKE 'race_%@test.com'))"
        ))
        conn.execute(text(
            "DELETE FROM list_shares WHERE list_id IN "
            "(SELECT id FROM lists WHERE owner_id IN "
            "(SELECT id FROM users WHERE email LIKE 'race_%@test.com'))"
        ))
        conn.execute(text(
            "DELETE FROM lists WHERE owner_id IN "
            "(SELECT id FROM users WHERE email LIKE 'race_%@test.com')"
        ))
        conn.execute(text(
            "DELETE FROM connections WHERE "
            "requester_id IN (SELECT id FROM users WHERE email LIKE 'race_%@test.com') "
            "OR addressee_id IN (SELECT id FROM users WHERE email LIKE 'race_%@test.com')"
        ))
        conn.execute(text("DELETE FROM users WHERE email LIKE 'race_%@test.com'"))
        conn.commit()

    # Pre-clean any leftover data from a previous failed run
    with _engine.connect() as pre_conn:
        _cleanup(pre_conn)

    # Set up data in a committed session so both request sessions can see it
    setup_db = SessionLocal()
    try:
        owner = User(email="race_owner@test.com", name="Race Owner", role="member", password_hash="x")
        owner.set_password("pass")
        claimer1 = User(email="race_claimer1@test.com", name="Claimer One", role="member", password_hash="x")
        claimer1.set_password("pass")
        claimer2 = User(email="race_claimer2@test.com", name="Claimer Two", role="member", password_hash="x")
        claimer2.set_password("pass")
        setup_db.add_all([owner, claimer1, claimer2])
        setup_db.flush()

        conn1 = Connection(requester_id=owner.id, addressee_id=claimer1.id, status="accepted")
        conn2 = Connection(requester_id=owner.id, addressee_id=claimer2.id, status="accepted")
        setup_db.add_all([conn1, conn2])
        setup_db.flush()

        race_list = GiftList(name="Race List", owner_id=owner.id)
        setup_db.add(race_list)
        setup_db.flush()

        share1 = ListShare(list_id=race_list.id, user_id=claimer1.id)
        share2 = ListShare(list_id=race_list.id, user_id=claimer2.id)
        setup_db.add_all([share1, share2])
        setup_db.flush()

        gift = Gift(list_id=race_list.id, name="Race Condition Gift")
        setup_db.add(gift)
        setup_db.flush()

        list_id = race_list.id
        gift_id = gift.id
        token1 = create_access_token(claimer1)
        token2 = create_access_token(claimer2)
        setup_db.commit()
    except Exception:
        setup_db.rollback()
        raise
    finally:
        setup_db.close()

    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}

    results = {}

    def claim_as(name, headers):
        # Each thread gets its own TestClient (and thus its own DB session via get_db)
        with TestClient(app) as c:
            resp = c.post(f"/lists/{list_id}/gifts/{gift_id}/claim", headers=headers)
            results[name] = resp.status_code

    t1 = threading.Thread(target=claim_as, args=("claimer1", headers1))
    t2 = threading.Thread(target=claim_as, args=("claimer2", headers2))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    codes = sorted(results.values())

    # Cleanup committed test data
    with _engine.connect() as post_conn:
        _cleanup(post_conn)

    assert codes == [200, 409], f"Expected [200, 409] but got {codes}"
