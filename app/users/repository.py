from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.connection import Connection
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.invite import Invite
from app.models.list_share import ListShare
from app.models.user import User


def get_all_users(db: Session) -> list[User]:
    return list(db.execute(select(User)).scalars().all())


def search_users(
    db: Session, query: str, exclude_user_id: int, limit: int = 10
) -> list[User]:
    pattern = f"%{query}%"
    return list(
        db.execute(
            select(User)
            .where(
                User.is_active.is_(True),
                User.id != exclude_user_id,
                or_(
                    User.email.ilike(pattern),
                    User.name.ilike(pattern),
                ),
            )
            .limit(limit)
        )
        .scalars()
        .all()
    )


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


def cascade_delete_user(db: Session, user: User) -> None:
    uid = user.id

    # Unclaim gifts this user claimed on others' lists
    db.execute(
        update(Gift)
        .where(Gift.claimed_by_id == uid)
        .values(claimed_by_id=None, claimed_at=None, purchased_at=None)
    )

    # Remove shares granted TO this user (and collection items referencing those shares)
    shared_list_ids = list(
        db.execute(
            select(ListShare.list_id).where(ListShare.user_id == uid)
        ).scalars().all()
    )
    if shared_list_ids:
        db.execute(
            delete(CollectionItem).where(
                CollectionItem.list_id.in_(shared_list_ids)
            )
        )
    db.execute(delete(ListShare).where(ListShare.user_id == uid))

    # Remove shares granted BY this user (on lists they own)
    owned_list_ids = list(
        db.execute(
            select(GiftList.id).where(GiftList.owner_id == uid)
        ).scalars().all()
    )
    if owned_list_ids:
        # Unclaim gifts on this user's lists
        db.execute(
            update(Gift)
            .where(Gift.list_id.in_(owned_list_ids), Gift.claimed_by_id.isnot(None))
            .values(claimed_by_id=None, claimed_at=None, purchased_at=None)
        )
        db.execute(
            delete(ListShare).where(ListShare.list_id.in_(owned_list_ids))
        )
        # Remove collection items referencing this user's lists
        db.execute(
            delete(CollectionItem).where(
                CollectionItem.list_id.in_(owned_list_ids)
            )
        )
        # Delete gifts then lists
        db.execute(delete(Gift).where(Gift.list_id.in_(owned_list_ids)))
        db.execute(delete(GiftList).where(GiftList.owner_id == uid))

    # Delete collections (items cascade via relationship)
    owned_collection_ids = list(
        db.execute(
            select(Collection.id).where(Collection.owner_id == uid)
        ).scalars().all()
    )
    if owned_collection_ids:
        db.execute(
            delete(CollectionItem).where(
                CollectionItem.collection_id.in_(owned_collection_ids)
            )
        )
        db.execute(delete(Collection).where(Collection.owner_id == uid))

    # Delete connections (both directions)
    db.execute(
        delete(Connection).where(
            or_(Connection.requester_id == uid, Connection.addressee_id == uid)
        )
    )

    # Delete invites created by this user and the invite they used to register
    db.execute(
        delete(Invite).where(
            or_(Invite.invited_by_id == uid, Invite.email == user.email)
        )
    )

    # Delete the user (password_reset_tokens cascade via DB)
    db.delete(user)
    db.flush()
