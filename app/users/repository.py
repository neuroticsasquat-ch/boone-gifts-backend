from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_all_users(db: Session) -> list[User]:
    return db.execute(select(User)).scalars().all()


def find_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def update_user(db: Session, user: User, updates: dict) -> User:
    for field, value in updates.items():
        setattr(user, field, value)
    db.flush()
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.flush()
