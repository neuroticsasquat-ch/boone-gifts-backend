from sqlalchemy.orm import Session

from app.models.user import User
from app.services.exceptions import BadRequestError, NotFoundError
from app.users import repository as repo


def list_users(db: Session) -> list[User]:
    return repo.get_all_users(db)


def get_user(db: Session, user_id: int) -> User:
    user = repo.find_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user


def update_user(
    db: Session, user_id: int, updates: dict, *, current_user_id: int
) -> User:
    if updates.get("is_active") is False and user_id == current_user_id:
        raise BadRequestError("Cannot deactivate your own account.")
    user = repo.find_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return repo.update_user(db, user, updates)


def search_users(db: Session, query: str, current_user_id: int) -> list[User]:
    return repo.search_users(db, query, exclude_user_id=current_user_id)


def delete_user(
    db: Session, user_id: int, *, current_user_id: int, purge: bool = False
) -> None:
    if user_id == current_user_id:
        raise BadRequestError("Cannot delete your own account.")
    user = repo.find_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    if purge:
        repo.cascade_delete_user(db, user)
    else:
        repo.delete_user(db, user)
