from sqlalchemy.orm import Session

from app.collections import repository as repo
from app.models.collection import Collection
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError


def create_collection(
    db: Session, name: str, description: str | None, owner_id: int
) -> Collection:
    return repo.create_collection(db, name, description, owner_id)


def list_collections(db: Session, owner_id: int, archived: bool = False) -> list[Collection]:
    return repo.get_collections_for_user(db, owner_id, archived=archived)


def get_collection_detail(db: Session, collection: Collection) -> dict:
    lists = repo.get_lists_for_collection(db, collection)
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "owner_id": collection.owner_id,
        "is_archived": collection.is_archived,
        "lists": lists,
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
    }


def update_collection(
    db: Session, collection: Collection, update_data: dict
) -> Collection:
    return repo.update_collection(db, collection, update_data)


def delete_collection(db: Session, collection: Collection) -> None:
    repo.delete_collection(db, collection)


def add_item(db: Session, collection: Collection, list_id: int, user_id: int) -> None:
    gift_list = repo.get_gift_list_by_id(db, list_id)
    if gift_list is None:
        raise NotFoundError("List not found.")

    if gift_list.owner_id != user_id:
        share = repo.find_share(db, list_id, user_id)
        if share is None:
            raise ForbiddenError("No access to this list.")

    existing = repo.find_collection_item(db, collection.id, list_id)
    if existing is not None:
        raise ConflictError("List already in collection.")

    repo.create_collection_item(db, collection.id, list_id)


def remove_item(db: Session, collection: Collection, list_id: int) -> None:
    item = repo.find_collection_item(db, collection.id, list_id)
    if item is None:
        raise NotFoundError("Item not found in collection.")
    repo.delete_collection_item(db, item)
