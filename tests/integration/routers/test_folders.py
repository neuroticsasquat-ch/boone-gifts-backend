def test_create_folder(client, member_user, member_headers):
    response = client.post(
        "/folders",
        headers=member_headers,
        json={"name": "Christmas 2026", "description": "Holiday gifts"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Christmas 2026"
    assert data["description"] == "Holiday gifts"
    assert data["owner_id"] == member_user.id


def test_create_folder_no_description(client, member_headers):
    response = client.post(
        "/folders",
        headers=member_headers,
        json={"name": "Birthdays"},
    )
    assert response.status_code == 201
    assert response.json()["description"] is None


def test_list_folders(client, member_headers, folder):
    response = client.get("/folders", headers=member_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Christmas 2026"


def test_list_folders_only_own(client, admin_headers, folder):
    response = client.get("/folders", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_get_folder_detail(
    client, member_headers, folder, folder_item, sample_list
):
    response = client.get(
        f"/folders/{folder.id}", headers=member_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Christmas 2026"
    assert len(data["lists"]) == 1
    assert data["lists"][0]["id"] == sample_list.id
    assert data["lists"][0]["name"] == "Member's Wishlist"


def test_get_folder_not_owner(client, admin_headers, folder):
    response = client.get(
        f"/folders/{folder.id}", headers=admin_headers
    )
    assert response.status_code == 403


def test_get_folder_not_found(client, member_headers):
    response = client.get("/folders/99999", headers=member_headers)
    assert response.status_code == 404


def test_update_folder(client, member_headers, folder):
    response = client.put(
        f"/folders/{folder.id}",
        headers=member_headers,
        json={"name": "Christmas 2027"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Christmas 2027"


def test_update_folder_not_owner(client, admin_headers, folder):
    response = client.put(
        f"/folders/{folder.id}",
        headers=admin_headers,
        json={"name": "Hacked"},
    )
    assert response.status_code == 403


def test_delete_folder(client, member_headers, folder):
    response = client.delete(
        f"/folders/{folder.id}", headers=member_headers
    )
    assert response.status_code == 204


def test_delete_folder_not_owner(client, admin_headers, folder):
    response = client.delete(
        f"/folders/{folder.id}", headers=admin_headers
    )
    assert response.status_code == 403


def test_add_owned_list(client, member_headers, folder, sample_list):
    response = client.post(
        f"/folders/{folder.id}/items",
        headers=member_headers,
        json={"list_id": sample_list.id},
    )
    assert response.status_code == 201


def test_add_shared_list(
    client, member_headers, folder, admin_user, connection, db
):
    from app.models.gift_list import GiftList
    from app.models.list_share import ListShare

    admin_list = GiftList(name="Admin's List", owner_id=admin_user.id)
    db.add(admin_list)
    db.flush()

    share = ListShare(list_id=admin_list.id, user_id=folder.owner_id)
    db.add(share)
    db.flush()

    response = client.post(
        f"/folders/{folder.id}/items",
        headers=member_headers,
        json={"list_id": admin_list.id},
    )
    assert response.status_code == 201


def test_add_inaccessible_list(
    client, member_headers, folder, admin_user, db
):
    from app.models.gift_list import GiftList

    admin_list = GiftList(name="Private List", owner_id=admin_user.id)
    db.add(admin_list)
    db.flush()

    response = client.post(
        f"/folders/{folder.id}/items",
        headers=member_headers,
        json={"list_id": admin_list.id},
    )
    assert response.status_code == 403


def test_add_nonexistent_list(client, member_headers, folder):
    response = client.post(
        f"/folders/{folder.id}/items",
        headers=member_headers,
        json={"list_id": 99999},
    )
    assert response.status_code == 404


def test_add_duplicate_item(client, member_headers, folder, folder_item, sample_list):
    response = client.post(
        f"/folders/{folder.id}/items",
        headers=member_headers,
        json={"list_id": sample_list.id},
    )
    assert response.status_code == 409


def test_remove_item(client, member_headers, folder, folder_item, sample_list):
    response = client.delete(
        f"/folders/{folder.id}/items/{sample_list.id}",
        headers=member_headers,
    )
    assert response.status_code == 204


def test_remove_item_not_found(client, member_headers, folder):
    response = client.delete(
        f"/folders/{folder.id}/items/99999",
        headers=member_headers,
    )
    assert response.status_code == 404


def test_archive_folder(client, member_headers, folder):
    response = client.put(
        f"/folders/{folder.id}",
        headers=member_headers,
        json={"is_archived": True},
    )
    assert response.status_code == 200
    assert response.json()["is_archived"] is True


def test_folders_exclude_archived_by_default(client, member_headers, folder, db):
    folder.is_archived = True
    db.flush()

    response = client.get("/folders", headers=member_headers)
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_folders_archived_filter(client, member_headers, folder, db):
    folder.is_archived = True
    db.flush()

    response = client.get("/folders?archived=true", headers=member_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_folders_for_list(client, member_headers, folder, folder_item, sample_list):
    response = client.get(f"/folders/for-list/{sample_list.id}", headers=member_headers)
    assert response.status_code == 200
    assert folder.id in response.json()


def test_folders_for_list_empty(client, member_headers, sample_list):
    response = client.get(f"/folders/for-list/{sample_list.id}", headers=member_headers)
    assert response.status_code == 200
    assert response.json() == []


# Shopping list endpoint tests

def test_shopping_list_returns_claimed_gifts(
    client, member_user, member_headers, admin_user, folder, folder_item, shared_list, db
):
    from app.models.gift import Gift

    gift = Gift(list_id=shared_list.id, name="Claimed by Member")
    gift.claimed_by_id = member_user.id
    db.add(gift)
    db.flush()

    response = client.get(
        f"/folders/{folder.id}/shopping-list",
        headers=member_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Claimed by Member"
    assert data[0]["list_name"] == shared_list.name
    assert data[0]["purchased_at"] is None


def test_shopping_list_excludes_unclaimed(
    client, member_headers, folder, folder_item, shared_list, db
):
    from app.models.gift import Gift

    gift = Gift(list_id=shared_list.id, name="Unclaimed Gift")
    db.add(gift)
    db.flush()

    response = client.get(
        f"/folders/{folder.id}/shopping-list",
        headers=member_headers,
    )
    assert response.status_code == 200
    assert response.json() == []


def test_shopping_list_excludes_other_claimer(
    client, member_headers, admin_user, folder, folder_item, shared_list, db
):
    from app.models.gift import Gift

    gift = Gift(list_id=shared_list.id, name="Admin's Claim")
    gift.claimed_by_id = admin_user.id
    db.add(gift)
    db.flush()

    response = client.get(
        f"/folders/{folder.id}/shopping-list",
        headers=member_headers,
    )
    assert response.status_code == 200
    assert response.json() == []


def test_shopping_list_shows_purchased_at(
    client, member_user, member_headers, folder, folder_item, shared_list, db
):
    from datetime import datetime, timezone
    from app.models.gift import Gift

    gift = Gift(list_id=shared_list.id, name="Bought Gift")
    gift.claimed_by_id = member_user.id
    gift.purchased_at = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)
    db.add(gift)
    db.flush()

    response = client.get(
        f"/folders/{folder.id}/shopping-list",
        headers=member_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["purchased_at"] is not None


def test_shopping_list_not_owner_403(client, admin_headers, folder):
    response = client.get(
        f"/folders/{folder.id}/shopping-list",
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_add_occasion_visible_list(
    client, member_user, member_headers, admin_user, folder, db
):
    from app.models.family import Family
    from app.models.family_member import FamilyMember
    from app.models.gift_list import GiftList
    from app.models.list_occasion_share import ListOccasionShare
    from app.models.occasion import Occasion

    # member_user (folder owner) and admin_user share a family, and admin_user
    # shared the list to its occasion. No connection, no direct ListShare —
    # visibility comes only from that occasion share.
    family = Family(name="The Boones", created_by_id=admin_user.id)
    db.add(family)
    db.flush()
    db.add_all(
        [
            FamilyMember(family_id=family.id, user_id=admin_user.id, role="organizer"),
            FamilyMember(family_id=family.id, user_id=member_user.id, role="member"),
        ]
    )
    db.flush()

    occasion = Occasion(
        family_id=family.id, name="Christmas 2026", created_by_id=admin_user.id
    )
    db.add(occasion)
    db.flush()

    admin_list = GiftList(name="Admin's Family List", owner_id=admin_user.id)
    db.add(admin_list)
    db.flush()
    db.add(ListOccasionShare(list_id=admin_list.id, occasion_id=occasion.id))
    db.flush()

    response = client.post(
        f"/folders/{folder.id}/items",
        headers=member_headers,
        json={"list_id": admin_list.id},
    )
    assert response.status_code == 201

    detail = client.get(f"/folders/{folder.id}", headers=member_headers)
    assert admin_list.id in {item["id"] for item in detail.json()["lists"]}
