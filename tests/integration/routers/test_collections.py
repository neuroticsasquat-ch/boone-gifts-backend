def test_create_collection(client, member_user, member_headers):
    response = client.post(
        "/collections",
        headers=member_headers,
        json={"name": "Christmas 2026", "description": "Holiday gifts"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Christmas 2026"
    assert data["description"] == "Holiday gifts"
    assert data["owner_id"] == member_user.id


def test_create_collection_no_description(client, member_headers):
    response = client.post(
        "/collections",
        headers=member_headers,
        json={"name": "Birthdays"},
    )
    assert response.status_code == 201
    assert response.json()["description"] is None


def test_list_collections(client, member_headers, collection):
    response = client.get("/collections", headers=member_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Christmas 2026"


def test_list_collections_only_own(client, admin_headers, collection):
    response = client.get("/collections", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_get_collection_detail(
    client, member_headers, collection, collection_item, sample_list
):
    response = client.get(
        f"/collections/{collection.id}", headers=member_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Christmas 2026"
    assert len(data["lists"]) == 1
    assert data["lists"][0]["id"] == sample_list.id
    assert data["lists"][0]["name"] == "Member's Wishlist"


def test_get_collection_not_owner(client, admin_headers, collection):
    response = client.get(
        f"/collections/{collection.id}", headers=admin_headers
    )
    assert response.status_code == 403


def test_get_collection_not_found(client, member_headers):
    response = client.get("/collections/99999", headers=member_headers)
    assert response.status_code == 404


def test_update_collection(client, member_headers, collection):
    response = client.put(
        f"/collections/{collection.id}",
        headers=member_headers,
        json={"name": "Christmas 2027"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Christmas 2027"


def test_update_collection_not_owner(client, admin_headers, collection):
    response = client.put(
        f"/collections/{collection.id}",
        headers=admin_headers,
        json={"name": "Hacked"},
    )
    assert response.status_code == 403


def test_delete_collection(client, member_headers, collection):
    response = client.delete(
        f"/collections/{collection.id}", headers=member_headers
    )
    assert response.status_code == 204


def test_delete_collection_not_owner(client, admin_headers, collection):
    response = client.delete(
        f"/collections/{collection.id}", headers=admin_headers
    )
    assert response.status_code == 403


def test_add_owned_list(client, member_headers, collection, sample_list):
    response = client.post(
        f"/collections/{collection.id}/items",
        headers=member_headers,
        json={"list_id": sample_list.id},
    )
    assert response.status_code == 201


def test_add_shared_list(
    client, member_headers, collection, admin_user, connection, db
):
    from app.models.gift_list import GiftList
    from app.models.list_share import ListShare

    admin_list = GiftList(name="Admin's List", owner_id=admin_user.id)
    db.add(admin_list)
    db.flush()

    share = ListShare(list_id=admin_list.id, user_id=collection.owner_id)
    db.add(share)
    db.flush()

    response = client.post(
        f"/collections/{collection.id}/items",
        headers=member_headers,
        json={"list_id": admin_list.id},
    )
    assert response.status_code == 201


def test_add_inaccessible_list(
    client, member_headers, collection, admin_user, db
):
    from app.models.gift_list import GiftList

    admin_list = GiftList(name="Private List", owner_id=admin_user.id)
    db.add(admin_list)
    db.flush()

    response = client.post(
        f"/collections/{collection.id}/items",
        headers=member_headers,
        json={"list_id": admin_list.id},
    )
    assert response.status_code == 403


def test_add_nonexistent_list(client, member_headers, collection):
    response = client.post(
        f"/collections/{collection.id}/items",
        headers=member_headers,
        json={"list_id": 99999},
    )
    assert response.status_code == 404


def test_add_duplicate_item(client, member_headers, collection, collection_item, sample_list):
    response = client.post(
        f"/collections/{collection.id}/items",
        headers=member_headers,
        json={"list_id": sample_list.id},
    )
    assert response.status_code == 409


def test_remove_item(client, member_headers, collection, collection_item, sample_list):
    response = client.delete(
        f"/collections/{collection.id}/items/{sample_list.id}",
        headers=member_headers,
    )
    assert response.status_code == 204


def test_remove_item_not_found(client, member_headers, collection):
    response = client.delete(
        f"/collections/{collection.id}/items/99999",
        headers=member_headers,
    )
    assert response.status_code == 404
