from sqlalchemy.orm import Session

from app.connections.repository import find_accepted_connection_between
from app.models.list_share import ListShare
from app.shares import repository as repo
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)


def create_share(
    db: Session, list_id: int, user_id: int, current_user_id: int
) -> ListShare:
    if user_id == current_user_id:
        raise BadRequestError("Cannot share a list with yourself.")

    connection = find_accepted_connection_between(db, current_user_id, user_id)
    if connection is None:
        raise ForbiddenError("You must be connected to share a list with this user.")

    existing = repo.find_share(db, list_id, user_id)
    if existing is not None:
        raise ConflictError("Share already exists.")

    return repo.create_share(db, list_id, user_id)


def list_shares(db: Session, list_id: int) -> list[ListShare]:
    return repo.get_shares_for_list(db, list_id)


def delete_share(db: Session, list_id: int, user_id: int) -> None:
    share = repo.find_share(db, list_id, user_id)
    if share is None:
        raise NotFoundError("Share not found.")

    repo.delete_share(db, share)

    items = repo.find_collection_items_for_unshare(db, list_id, user_id)
    for item in items:
        repo.delete_collection_item(db, item)
