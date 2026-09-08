from sqlalchemy.orm import Session

from app.access import can_view_list
from app.occasions import repository as repo
from app.models.occasion import Occasion
from app.models.user import User
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError


def create_occasion(
    db: Session, name: str, description: str | None, owner_id: int
) -> Occasion:
    return repo.create_occasion(db, name, description, owner_id)


def list_occasions(db: Session, owner_id: int, archived: bool = False) -> list[Occasion]:
    return repo.get_occasions_for_user(db, owner_id, archived=archived)


def get_occasion_detail(db: Session, occasion: Occasion) -> dict:
    lists = repo.get_lists_for_occasion(db, occasion)
    return {
        "id": occasion.id,
        "name": occasion.name,
        "description": occasion.description,
        "owner_id": occasion.owner_id,
        "is_archived": occasion.is_archived,
        "lists": lists,
        "created_at": occasion.created_at,
        "updated_at": occasion.updated_at,
    }


def update_occasion(
    db: Session, occasion: Occasion, update_data: dict
) -> Occasion:
    return repo.update_occasion(db, occasion, update_data)


def delete_occasion(db: Session, occasion: Occasion) -> None:
    repo.delete_occasion(db, occasion)


def add_item(db: Session, occasion: Occasion, list_id: int, user: User) -> None:
    gift_list = repo.get_gift_list_by_id(db, list_id)
    if gift_list is None:
        raise NotFoundError("List not found.")

    if not can_view_list(db, user, gift_list):
        raise ForbiddenError("No access to this list.")

    existing = repo.find_occasion_item(db, occasion.id, list_id)
    if existing is not None:
        raise ConflictError("List already in occasion.")

    repo.create_occasion_item(db, occasion.id, list_id)


def remove_item(db: Session, occasion: Occasion, list_id: int) -> None:
    item = repo.find_occasion_item(db, occasion.id, list_id)
    if item is None:
        raise NotFoundError("Item not found in occasion.")
    repo.delete_occasion_item(db, item)


def get_occasion_ids_for_list(db: Session, list_id: int, owner_id: int) -> list[int]:
    return repo.get_occasion_ids_for_list(db, list_id, owner_id)


def get_shopping_list(db: Session, occasion_id: int, user_id: int) -> list[dict]:
    return repo.get_shopping_list_items(db, occasion_id, user_id)
