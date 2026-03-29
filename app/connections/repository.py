from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.connection import Connection
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.models.user import User


def find_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()


def find_connection_between(db: Session, user_a_id: int, user_b_id: int) -> Connection | None:
    return db.execute(
        select(Connection).where(
            or_(
                (Connection.requester_id == user_a_id)
                & (Connection.addressee_id == user_b_id),
                (Connection.requester_id == user_b_id)
                & (Connection.addressee_id == user_a_id),
            )
        )
    ).scalar_one_or_none()


def find_accepted_connection_between(db: Session, user_a_id: int, user_b_id: int) -> Connection | None:
    return db.execute(
        select(Connection).where(
            Connection.status == "accepted",
            or_(
                (Connection.requester_id == user_a_id)
                & (Connection.addressee_id == user_b_id),
                (Connection.requester_id == user_b_id)
                & (Connection.addressee_id == user_a_id),
            ),
        )
    ).scalar_one_or_none()


def find_connection_by_id(db: Session, connection_id: int) -> Connection | None:
    return db.get(Connection, connection_id)


def get_accepted_connections(db: Session, user_id: int) -> list[Connection]:
    return db.execute(
        select(Connection).where(
            Connection.status == "accepted",
            or_(
                Connection.requester_id == user_id,
                Connection.addressee_id == user_id,
            ),
        )
    ).scalars().all()


def get_pending_requests(db: Session, user_id: int) -> list[Connection]:
    return db.execute(
        select(Connection).where(
            Connection.status == "pending",
            Connection.addressee_id == user_id,
        )
    ).scalars().all()


def create_connection(db: Session, requester_id: int, addressee_id: int) -> Connection:
    connection = Connection(requester_id=requester_id, addressee_id=addressee_id)
    db.add(connection)
    db.flush()
    return connection


def update_connection_accepted(db: Session, connection: Connection) -> Connection:
    connection.status = "accepted"
    connection.accepted_at = datetime.now(timezone.utc)
    db.flush()
    return connection


def delete_connection(db: Session, connection: Connection) -> None:
    db.delete(connection)
    db.flush()


def unclaim_gifts_between(db: Session, user_a_id: int, user_b_id: int) -> None:
    list_ids_a = select(GiftList.id).where(GiftList.owner_id == user_a_id)
    list_ids_b = select(GiftList.id).where(GiftList.owner_id == user_b_id)

    db.execute(
        update(Gift)
        .where(Gift.list_id.in_(list_ids_a), Gift.claimed_by_id == user_b_id)
        .values(claimed_by_id=None, claimed_at=None)
    )
    db.execute(
        update(Gift)
        .where(Gift.list_id.in_(list_ids_b), Gift.claimed_by_id == user_a_id)
        .values(claimed_by_id=None, claimed_at=None)
    )


def delete_shares_between(db: Session, user_a_id: int, user_b_id: int) -> None:
    list_ids_a = select(GiftList.id).where(GiftList.owner_id == user_a_id)
    list_ids_b = select(GiftList.id).where(GiftList.owner_id == user_b_id)

    shares = db.execute(
        select(ListShare).where(
            or_(
                (ListShare.list_id.in_(list_ids_a)) & (ListShare.user_id == user_b_id),
                (ListShare.list_id.in_(list_ids_b)) & (ListShare.user_id == user_a_id),
            )
        )
    ).scalars().all()
    for share in shares:
        db.delete(share)


def delete_collection_items_between(db: Session, user_a_id: int, user_b_id: int) -> None:
    list_ids_a = select(GiftList.id).where(GiftList.owner_id == user_a_id)
    list_ids_b = select(GiftList.id).where(GiftList.owner_id == user_b_id)
    collection_ids_a = select(Collection.id).where(Collection.owner_id == user_a_id)
    collection_ids_b = select(Collection.id).where(Collection.owner_id == user_b_id)

    items = db.execute(
        select(CollectionItem).where(
            or_(
                (CollectionItem.collection_id.in_(collection_ids_a))
                & (CollectionItem.list_id.in_(list_ids_b)),
                (CollectionItem.collection_id.in_(collection_ids_b))
                & (CollectionItem.list_id.in_(list_ids_a)),
            )
        )
    ).scalars().all()
    for item in items:
        db.delete(item)
