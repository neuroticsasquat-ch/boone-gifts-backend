from sqlalchemy.orm import Session

from app.access import can_view_list
from app.claims import repository as claims_repo
from app.folders import repository as repo
from app.lists import service as list_service
from app.models.folder import Folder
from app.models.user import User
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError


def create_folder(
    db: Session, name: str, description: str | None, owner_id: int
) -> Folder:
    return repo.create_folder(db, name, description, owner_id)


def list_folders(db: Session, owner_id: int, archived: bool = False) -> list[Folder]:
    return repo.get_folders_for_user(db, owner_id, archived=archived)


def get_folder_detail(db: Session, folder: Folder) -> dict:
    # A folder groups lists its owner mostly does *not* own, so each row is
    # serialized for them individually — the shared ones keep `claimed_count`,
    # the caller's own carry no claim state at all.
    lists = [
        list_service.to_summary(gift_list, folder.owner_id)
        for gift_list in repo.get_lists_for_folder(db, folder)
    ]
    return {
        "id": folder.id,
        "name": folder.name,
        "description": folder.description,
        "owner_id": folder.owner_id,
        "is_archived": folder.is_archived,
        "lists": lists,
        "created_at": folder.created_at,
        "updated_at": folder.updated_at,
    }


def update_folder(
    db: Session, folder: Folder, update_data: dict
) -> Folder:
    return repo.update_folder(db, folder, update_data)


def delete_folder(db: Session, folder: Folder) -> None:
    repo.delete_folder(db, folder)


def add_item(db: Session, folder: Folder, list_id: int, user: User) -> None:
    gift_list = repo.get_gift_list_by_id(db, list_id)
    if gift_list is None:
        raise NotFoundError("List not found.")

    if not can_view_list(db, user, gift_list):
        raise ForbiddenError("No access to this list.")

    existing = repo.find_folder_item(db, folder.id, list_id)
    if existing is not None:
        raise ConflictError("List already in folder.")

    repo.create_folder_item(db, folder.id, list_id)


def remove_item(db: Session, folder: Folder, list_id: int) -> None:
    item = repo.find_folder_item(db, folder.id, list_id)
    if item is None:
        raise NotFoundError("Item not found in folder.")
    repo.delete_folder_item(db, item)


def get_folder_ids_for_list(db: Session, list_id: int, owner_id: int) -> list[int]:
    return repo.get_folder_ids_for_list(db, list_id, owner_id)


def get_shopping(db: Session, folder_id: int, user_id: int) -> list[dict]:
    """The folder's shopping tab. The query lives with the other claim queries
    (`app/claims/repository.py`), not here."""
    return claims_repo.get_shopping_for_folder(db, folder_id, user_id)
