from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.folder import Folder
from app.models.folder_item import FolderItem
from app.models.list_share import ListShare
from app.models.user import User


def find_share(db: Session, list_id: int, user_id: int) -> ListShare | None:
    return db.execute(
        select(ListShare).where(
            ListShare.list_id == list_id,
            ListShare.user_id == user_id,
        )
    ).scalar_one_or_none()


def create_share(db: Session, list_id: int, user_id: int) -> ListShare:
    share = ListShare(list_id=list_id, user_id=user_id)
    db.add(share)
    db.flush()
    return share


def get_shares_for_list(db: Session, list_id: int) -> list[ListShare]:
    return list(
        db.execute(select(ListShare).where(ListShare.list_id == list_id))
        .scalars()
        .all()
    )


def get_shared_users(db: Session, list_id: int) -> list[User]:
    share_user_ids = select(ListShare.user_id).where(ListShare.list_id == list_id)
    return list(
        db.execute(select(User).where(User.id.in_(share_user_ids)))
        .scalars()
        .all()
    )


def delete_share(db: Session, share: ListShare) -> None:
    db.delete(share)
    db.flush()


def find_folder_items_for_unshare(
    db: Session, list_id: int, user_id: int
) -> list[FolderItem]:
    folder_ids = select(Folder.id).where(Folder.owner_id == user_id)
    return list(
        db.execute(
            select(FolderItem).where(
                FolderItem.folder_id.in_(folder_ids),
                FolderItem.list_id == list_id,
            )
        )
        .scalars()
        .all()
    )


def delete_folder_item(db: Session, item: FolderItem) -> None:
    db.delete(item)
