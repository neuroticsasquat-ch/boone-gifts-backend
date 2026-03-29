def test_share_list(client, member_user, member_headers, sample_list, admin_user, connection):
    response = client.post(
        f"/lists/{sample_list.id}/shares",
        headers=member_headers,
        json={"user_id": admin_user.id},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["list_id"] == sample_list.id
    assert data["user_id"] == admin_user.id


def test_share_list_not_owner(client, admin_headers, shared_list, db):
    from app.models.user import User

    other = User(email="other@test.com", name="Other", password_hash="h")
    db.add(other)
    db.flush()

    response = client.post(
        f"/lists/{shared_list.id}/shares",
        headers=admin_headers,
        json={"user_id": other.id},
    )
    assert response.status_code == 403


def test_share_list_with_self(client, member_user, member_headers, sample_list):
    response = client.post(
        f"/lists/{sample_list.id}/shares",
        headers=member_headers,
        json={"user_id": member_user.id},
    )
    assert response.status_code == 400


def test_share_list_duplicate(
    client, member_headers, shared_list, admin_user
):
    response = client.post(
        f"/lists/{shared_list.id}/shares",
        headers=member_headers,
        json={"user_id": admin_user.id},
    )
    assert response.status_code == 409


def test_list_shares(client, member_headers, shared_list, admin_user):
    response = client.get(
        f"/lists/{shared_list.id}/shares",
        headers=member_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["user_id"] == admin_user.id


def test_list_shares_not_owner(client, admin_headers, shared_list):
    response = client.get(
        f"/lists/{shared_list.id}/shares",
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_unshare_list(client, member_headers, shared_list, admin_user):
    response = client.delete(
        f"/lists/{shared_list.id}/shares/{admin_user.id}",
        headers=member_headers,
    )
    assert response.status_code == 204


def test_unshare_list_not_owner(client, admin_headers, shared_list, admin_user):
    response = client.delete(
        f"/lists/{shared_list.id}/shares/{admin_user.id}",
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_unshare_list_not_found(client, member_headers, sample_list):
    response = client.delete(
        f"/lists/{sample_list.id}/shares/99999",
        headers=member_headers,
    )
    assert response.status_code == 404


def test_share_list_not_connected(client, member_headers, sample_list, db):
    from app.models.user import User

    other = User(email="unconnected@test.com", name="Unconnected", password_hash="h")
    db.add(other)
    db.flush()

    response = client.post(
        f"/lists/{sample_list.id}/shares",
        headers=member_headers,
        json={"user_id": other.id},
    )
    assert response.status_code == 403


def test_share_list_connected(
    client, member_headers, sample_list, admin_user, connection
):
    response = client.post(
        f"/lists/{sample_list.id}/shares",
        headers=member_headers,
        json={"user_id": admin_user.id},
    )
    assert response.status_code == 201


def test_unshare_removes_collection_items(
    client, member_headers, shared_list, admin_user, db
):
    from app.models.collection import Collection
    from app.models.collection_item import CollectionItem

    admin_collection = Collection(name="Admin Collection", owner_id=admin_user.id)
    db.add(admin_collection)
    db.flush()

    item = CollectionItem(
        collection_id=admin_collection.id, list_id=shared_list.id
    )
    db.add(item)
    db.flush()

    response = client.delete(
        f"/lists/{shared_list.id}/shares/{admin_user.id}",
        headers=member_headers,
    )
    assert response.status_code == 204

    from sqlalchemy import select

    remaining = db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == admin_collection.id,
            CollectionItem.list_id == shared_list.id,
        )
    ).scalar_one_or_none()
    assert remaining is None
