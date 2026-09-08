from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_share import ListShare


def create_folder(
    db: Session, name: str, description: str | None, owner_id: int
) -> Folder:
    folder = Folder(name=name, description=description, owner_id=owner_id)
    db.add(folder)
    db.flush()
    return folder


def get_folders_for_user(db: Session, owner_id: int, archived: bool = False) -> list[Folder]:
    return list(
        db.execute(
            select(Folder).where(
                Folder.owner_id == owner_id,
                Folder.is_archived == archived,
            )
        )
        .scalars()
        .all()
    )


def get_folder_by_id(db: Session, folder_id: int) -> Folder | None:
    return db.get(Folder, folder_id)


def get_lists_for_folder(db: Session, folder: Folder) -> list[GiftList]:
    list_ids = [item.list_id for item in folder.items]
    if not list_ids:
        return []
    return list(
        db.execute(select(GiftList).where(GiftList.id.in_(list_ids))).scalars().all()
    )


def update_folder(
    db: Session, folder: Folder, update_data: dict
) -> Folder:
    for key, value in update_data.items():
        setattr(folder, key, value)
    db.flush()
    return folder


def delete_folder(db: Session, folder: Folder) -> None:
    db.delete(folder)
    db.flush()


def get_gift_list_by_id(db: Session, list_id: int) -> GiftList | None:
    return db.get(GiftList, list_id)


def find_share(db: Session, list_id: int, user_id: int) -> ListShare | None:
    return db.execute(
        select(ListShare).where(
            ListShare.list_id == list_id,
            ListShare.user_id == user_id,
        )
    ).scalar_one_or_none()


def find_folder_item(
    db: Session, folder_id: int, list_id: int
) -> FolderItem | None:
    return db.execute(
        select(FolderItem).where(
            FolderItem.folder_id == folder_id,
            FolderItem.list_id == list_id,
        )
    ).scalar_one_or_none()


def create_folder_item(
    db: Session, folder_id: int, list_id: int
) -> FolderItem:
    item = FolderItem(folder_id=folder_id, list_id=list_id)
    db.add(item)
    db.flush()
    return item


def delete_folder_item(db: Session, item: FolderItem) -> None:
    db.delete(item)
    db.flush()


def get_folder_ids_for_list(db: Session, list_id: int, owner_id: int) -> list[int]:
    result = db.execute(
        select(FolderItem.folder_id)
        .join(Folder, FolderItem.folder_id == Folder.id)
        .where(
            FolderItem.list_id == list_id,
            Folder.owner_id == owner_id,
        )
    ).scalars().all()
    return list(result)


def get_shopping_list_items(
    db: Session, folder_id: int, user_id: int
) -> list[dict]:
    """Return all gifts claimed by user_id within the given folder."""
    rows = db.execute(
        select(Gift, GiftList.name.label("list_name"))
        .join(GiftList, Gift.list_id == GiftList.id)
        .join(FolderItem, FolderItem.list_id == GiftList.id)
        .where(
            FolderItem.folder_id == folder_id,
            Gift.claimed_by_id == user_id,
        )
        .order_by(GiftList.id, Gift.id)
    ).all()
    return [
        {
            "id": gift.id,
            "name": gift.name,
            "description": gift.description,
            "url": gift.url,
            "price": gift.price,
            "list_id": gift.list_id,
            "list_name": list_name,
            "purchased_at": gift.purchased_at,
        }
        for gift, list_name in rows
    ]
