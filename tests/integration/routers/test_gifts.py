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
