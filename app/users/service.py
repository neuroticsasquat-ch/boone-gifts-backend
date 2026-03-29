from sqlalchemy.orm import Session

from app.models.user import User
from app.services.exceptions import NotFoundError
from app.users import repository as repo


def list_users(db: Session) -> list[User]:
    return repo.get_all_users(db)


def get_user(db: Session, user_id: int) -> User:
    user = repo.find_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user


def update_user(db: Session, user_id: int, updates: dict) -> User:
    user = repo.find_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return repo.update_user(db, user, updates)


def delete_user(db: Session, user_id: int) -> None:
    user = repo.find_user_by_id(db, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    repo.delete_user(db, user)
