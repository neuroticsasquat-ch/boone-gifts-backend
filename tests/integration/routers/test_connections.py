from app.models.connection import Connection


def test_send_request_by_user_id(client, member_user, member_headers, admin_user):
    response = client.post(
        "/connections",
        headers=member_headers,
        json={"user_id": admin_user.id},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["user"]["id"] == admin_user.id
    assert data["user"]["name"] == "Admin"


def test_send_request_by_email(client, member_user, member_headers, admin_user):
    response = client.post(
        "/connections",
        headers=member_headers,
        json={"email": "admin@test.com"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["user"]["email"] == "admin@test.com"


def test_send_request_to_self(client, member_user, member_headers):
    response = client.post(
        "/connections",
        headers=member_headers,
        json={"user_id": member_user.id},
    )
    assert response.status_code == 400


def test_send_request_duplicate(client, member_headers, admin_user, connection):
    response = client.post(
        "/connections",
        headers=member_headers,
        json={"user_id": admin_user.id},
    )
    assert response.status_code == 409


def test_send_request_nonexistent_user(client, member_headers):
    response = client.post(
        "/connections",
        headers=member_headers,
        json={"user_id": 99999},
    )
    assert response.status_code == 404


def test_send_request_nonexistent_email(client, member_headers):
    response = client.post(
        "/connections",
        headers=member_headers,
        json={"email": "nobody@test.com"},
    )
    assert response.status_code == 404


def test_list_connections(client, member_headers, admin_user, connection):
    response = client.get("/connections", headers=member_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["user"]["id"] == admin_user.id
    assert data[0]["status"] == "accepted"


def test_list_connections_excludes_pending(client, member_headers, admin_user, db):
    from app.models.user import User

    other = User(email="other@test.com", name="Other", password_hash="h")
    db.add(other)
    db.flush()

    pending = Connection(requester_id=other.id, addressee_id=admin_user.id)
    db.add(pending)
    db.flush()

    response = client.get("/connections", headers=member_headers)
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_list_pending_requests(client, member_user, member_headers, admin_user, db):
    pending = Connection(requester_id=admin_user.id, addressee_id=member_user.id)
    db.add(pending)
    db.flush()

    response = client.get("/connections/requests", headers=member_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["user"]["id"] == admin_user.id
    assert data[0]["status"] == "pending"


def test_list_pending_excludes_sent(client, member_user, member_headers, admin_user, db):
    sent = Connection(requester_id=member_user.id, addressee_id=admin_user.id)
    db.add(sent)
    db.flush()

    response = client.get("/connections/requests", headers=member_headers)
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_accept_request(client, member_user, member_headers, admin_user, db):
    pending = Connection(requester_id=admin_user.id, addressee_id=member_user.id)
    db.add(pending)
    db.flush()

    response = client.post(
        f"/connections/{pending.id}/accept",
        headers=member_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["accepted_at"] is not None


def test_accept_request_not_addressee(client, admin_headers, member_user, admin_user, db):
    pending = Connection(requester_id=admin_user.id, addressee_id=member_user.id)
    db.add(pending)
    db.flush()

    response = client.post(
        f"/connections/{pending.id}/accept",
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_accept_already_accepted(client, member_headers, connection):
    response = client.post(
        f"/connections/{connection.id}/accept",
        headers=member_headers,
    )
    assert response.status_code == 409


def test_delete_pending_request(client, member_user, member_headers, admin_user, db):
    pending = Connection(requester_id=admin_user.id, addressee_id=member_user.id)
    db.add(pending)
    db.flush()

    response = client.delete(
        f"/connections/{pending.id}",
        headers=member_headers,
    )
    assert response.status_code == 204


def test_delete_connection(client, member_headers, connection):
    response = client.delete(
        f"/connections/{connection.id}",
        headers=member_headers,
    )
    assert response.status_code == 204


def test_delete_connection_not_party(client, member_user, admin_user, db):
    from app.models.user import User
    from app.dependencies import create_access_token

    other = User(email="other2@test.com", name="Other", password_hash="h")
    other.set_password("other123")
    db.add(other)
    db.flush()

    conn = Connection(
        requester_id=admin_user.id,
        addressee_id=member_user.id,
        status="accepted",
    )
    db.add(conn)
    db.flush()

    other_token = create_access_token(other)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    from fastapi.testclient import TestClient
    from app.main import app
    from app.dependencies import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        response = c.delete(f"/connections/{conn.id}", headers=other_headers)
    app.dependency_overrides.clear()

    assert response.status_code == 403


def test_delete_connection_not_found(client, member_headers):
    response = client.delete("/connections/99999", headers=member_headers)
    assert response.status_code == 404


def test_disconnect_revokes_shares(
    client, member_user, member_headers, admin_user, connection, db
):
    from app.models.gift_list import GiftList
    from app.models.list_share import ListShare

    gift_list = GiftList(name="Shared List", owner_id=member_user.id)
    db.add(gift_list)
    db.flush()

    share = ListShare(list_id=gift_list.id, user_id=admin_user.id)
    db.add(share)
    db.flush()

    response = client.delete(
        f"/connections/{connection.id}",
        headers=member_headers,
    )
    assert response.status_code == 204

    from sqlalchemy import select

    remaining = db.execute(
        select(ListShare).where(
            ListShare.list_id == gift_list.id,
            ListShare.user_id == admin_user.id,
        )
    ).scalar_one_or_none()
    assert remaining is None


def test_disconnect_unclaims_gifts(
    client, member_user, member_headers, admin_user, connection, db
):
    from app.models.gift_list import GiftList
    from app.models.gift import Gift
    from app.models.list_share import ListShare

    gift_list = GiftList(name="Claimed List", owner_id=member_user.id)
    db.add(gift_list)
    db.flush()

    share = ListShare(list_id=gift_list.id, user_id=admin_user.id)
    db.add(share)
    db.flush()

    gift = Gift(
        list_id=gift_list.id,
        name="Claimed Gift",
        claimed_by_id=admin_user.id,
    )
    db.add(gift)
    db.flush()

    response = client.delete(
        f"/connections/{connection.id}",
        headers=member_headers,
    )
    assert response.status_code == 204

    db.refresh(gift)
    assert gift.claimed_by_id is None
    assert gift.claimed_at is None


def test_disconnect_removes_collection_items(
    client, member_user, member_headers, admin_user, connection, db
):
    from app.models.gift_list import GiftList
    from app.models.list_share import ListShare
    from app.models.collection import Collection
    from app.models.collection_item import CollectionItem

    admin_list = GiftList(name="Admin's List", owner_id=admin_user.id)
    db.add(admin_list)
    db.flush()

    share = ListShare(list_id=admin_list.id, user_id=member_user.id)
    db.add(share)
    db.flush()

    member_collection = Collection(
        name="Member Collection", owner_id=member_user.id
    )
    db.add(member_collection)
    db.flush()

    item = CollectionItem(
        collection_id=member_collection.id, list_id=admin_list.id
    )
    db.add(item)
    db.flush()

    response = client.delete(
        f"/connections/{connection.id}",
        headers=member_headers,
    )
    assert response.status_code == 204

    from sqlalchemy import select

    remaining = db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == member_collection.id,
            CollectionItem.list_id == admin_list.id,
        )
    ).scalar_one_or_none()
    assert remaining is None
