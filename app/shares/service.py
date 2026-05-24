from sqlalchemy.orm import Session

from app.config import settings
from app.connections.repository import find_accepted_connection_between
from app.email.list_shared import render_list_shared_email
from app.email.sender import send_email
from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.models.user import User
from app.shares import repository as repo
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)


def create_share(
    db: Session, list_id: int, user_id: int, current_user_id: int
) -> ListShare:
    if user_id == current_user_id:
        raise BadRequestError("Cannot share a list with yourself.")

    connection = find_accepted_connection_between(db, current_user_id, user_id)
    if connection is None:
        raise ForbiddenError("You must be connected to share a list with this user.")

    existing = repo.find_share(db, list_id, user_id)
    if existing is not None:
        raise ConflictError("Share already exists.")

    share = repo.create_share(db, list_id, user_id)

    recipient = db.get(User, user_id)
    sharer = db.get(User, current_user_id)
    gift_list = db.get(GiftList, list_id)
    if recipient and recipient.is_active and sharer and gift_list:
        base = settings.frontend_url.rstrip("/")
        list_url = f"{base}/lists/{list_id}"
        subject, html, text = render_list_shared_email(
            sharer_name=sharer.name,
            list_name=gift_list.name,
            list_url=list_url,
        )
        send_email(to=recipient.email, subject=subject, html=html, text=text)

    return share


def list_shares(db: Session, list_id: int) -> list[ListShare]:
    return repo.get_shares_for_list(db, list_id)


def delete_share(db: Session, list_id: int, user_id: int) -> None:
    share = repo.find_share(db, list_id, user_id)
    if share is None:
        raise NotFoundError("Share not found.")

    repo.delete_share(db, share)

    items = repo.find_collection_items_for_unshare(db, list_id, user_id)
    for item in items:
        repo.delete_collection_item(db, item)
