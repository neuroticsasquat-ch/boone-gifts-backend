from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.list_share import ListShare


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


def delete_share(db: Session, share: ListShare) -> None:
    db.delete(share)
    db.flush()


def find_collection_items_for_unshare(
    db: Session, list_id: int, user_id: int
) -> list[CollectionItem]:
    collection_ids = select(Collection.id).where(Collection.owner_id == user_id)
    return list(
        db.execute(
            select(CollectionItem).where(
                CollectionItem.collection_id.in_(collection_ids),
                CollectionItem.list_id == list_id,
            )
        )
        .scalars()
        .all()
    )


def delete_collection_item(db: Session, item: CollectionItem) -> None:
    db.delete(item)
