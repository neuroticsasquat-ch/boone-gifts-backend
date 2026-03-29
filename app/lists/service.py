from sqlalchemy.orm import Session

from app.lists import repository as repo
from app.models.gift_list import GiftList
from app.schemas.gift_list import GiftListDetailOwner, GiftListDetailViewer


def create_list(
    db: Session, name: str, description: str | None, owner_id: int
) -> GiftList:
    return repo.create_list(db, name=name, description=description, owner_id=owner_id)


def get_lists(db: Session, user_id: int, filter: str | None = None) -> list[GiftList]:
    if filter == "owned":
        return repo.get_lists_by_owner(db, user_id)
    elif filter == "shared":
        return repo.get_shared_lists(db, user_id)
    else:
        return repo.get_all_visible_lists(db, user_id)


def get_list(
    gift_list: GiftList, user_id: int
) -> GiftListDetailOwner | GiftListDetailViewer:
    if gift_list.owner_id == user_id:
        return GiftListDetailOwner.model_validate(gift_list)
    return GiftListDetailViewer.model_validate(gift_list)


def update_list(db: Session, gift_list: GiftList, updates: dict) -> GiftList:
    return repo.update_list(db, gift_list, updates)


def delete_list(db: Session, gift_list: GiftList) -> None:
    repo.delete_list(db, gift_list)
