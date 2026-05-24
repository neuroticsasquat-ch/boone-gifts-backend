from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.gift_list import GiftList
from app.models.list_share import ListShare


def create_collection(
    db: Session, name: str, description: str | None, owner_id: int
) -> Collection:
    collection = Collection(name=name, description=description, owner_id=owner_id)
    db.add(collection)
    db.flush()
    return collection


def get_collections_for_user(db: Session, owner_id: int, archived: bool = False) -> list[Collection]:
    return list(
        db.execute(
            select(Collection).where(
                Collection.owner_id == owner_id,
                Collection.is_archived == archived,
            )
        )
        .scalars()
        .all()
    )


def get_collection_by_id(db: Session, collection_id: int) -> Collection | None:
    return db.get(Collection, collection_id)


def get_lists_for_collection(db: Session, collection: Collection) -> list[GiftList]:
    list_ids = [item.list_id for item in collection.items]
    if not list_ids:
        return []
    return list(
        db.execute(select(GiftList).where(GiftList.id.in_(list_ids))).scalars().all()
    )


def update_collection(
    db: Session, collection: Collection, update_data: dict
) -> Collection:
    for key, value in update_data.items():
        setattr(collection, key, value)
    db.flush()
    return collection


def delete_collection(db: Session, collection: Collection) -> None:
    db.delete(collection)
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


def find_collection_item(
    db: Session, collection_id: int, list_id: int
) -> CollectionItem | None:
    return db.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.list_id == list_id,
        )
    ).scalar_one_or_none()


def create_collection_item(
    db: Session, collection_id: int, list_id: int
) -> CollectionItem:
    item = CollectionItem(collection_id=collection_id, list_id=list_id)
    db.add(item)
    db.flush()
    return item


def delete_collection_item(db: Session, item: CollectionItem) -> None:
    db.delete(item)
    db.flush()
