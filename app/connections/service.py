from sqlalchemy.orm import Session

from app.config import settings
from app.connections import repository as repo
from app.email.connection_request import render_connection_request_email
from app.email.sender import send_email
from app.models.connection import Connection
from app.models.user import User
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)


def build_connection_response(
    db: Session, connection: Connection, current_user_id: int
) -> dict:
    other_id = (
        connection.addressee_id
        if connection.requester_id == current_user_id
        else connection.requester_id
    )
    other_user = repo.find_user_by_id(db, other_id)
    if other_user is None:
        raise NotFoundError("User not found.")

    return {
        "id": connection.id,
        "status": connection.status,
        "user": {
            "id": other_user.id,
            "name": other_user.name,
            "email": other_user.email,
        },
        "created_at": connection.created_at,
        "accepted_at": connection.accepted_at,
    }


def create_connection(
    db: Session,
    requester_id: int,
    target_user_id: int | None = None,
    target_email: str | None = None,
) -> dict:
    target: User | None
    if target_user_id is not None:
        target = repo.find_user_by_id(db, target_user_id)
    else:
        if target_email is None:
            raise NotFoundError("Target user not found.")
        target = repo.find_user_by_email(db, target_email)

    if target is None:
        raise NotFoundError("User not found.")

    if target.id == requester_id:
        raise BadRequestError("Cannot connect with yourself.")

    existing = repo.find_connection_between(db, requester_id, target.id)
    if existing is not None:
        raise ConflictError("Connection already exists.")

    connection = repo.create_connection(db, requester_id, target.id)

    requester = repo.find_user_by_id(db, requester_id)
    if target.is_active and requester:
        subject, html, text = render_connection_request_email(
            sender_name=requester.name,
            frontend_url=settings.frontend_url,
        )
        send_email(to=target.email, subject=subject, html=html, text=text)

    return build_connection_response(db, connection, requester_id)


def list_connections(db: Session, user_id: int) -> list[dict]:
    connections = repo.get_accepted_connections(db, user_id)
    return [build_connection_response(db, c, user_id) for c in connections]


def list_requests(db: Session, user_id: int) -> list[dict]:
    connections = repo.get_pending_requests(db, user_id)
    return [build_connection_response(db, c, user_id) for c in connections]


def accept_connection(db: Session, connection_id: int, user_id: int) -> dict:
    connection = repo.find_connection_by_id(db, connection_id)
    if connection is None:
        raise NotFoundError("Connection not found.")
    if connection.addressee_id != user_id:
        raise ForbiddenError("Only the addressee can accept.")
    if connection.status == "accepted":
        raise ConflictError("Already accepted.")

    repo.update_connection_accepted(db, connection)
    return build_connection_response(db, connection, user_id)


def delete_connection(db: Session, connection_id: int, user_id: int) -> None:
    connection = repo.find_connection_by_id(db, connection_id)
    if connection is None:
        raise NotFoundError("Connection not found.")
    if connection.requester_id != user_id and connection.addressee_id != user_id:
        raise ForbiddenError("Not a party to this connection.")

    if connection.status == "accepted":
        cascade_disconnect(db, connection.requester_id, connection.addressee_id)

    repo.delete_connection(db, connection)


def cascade_disconnect(db: Session, user_a_id: int, user_b_id: int) -> None:
    repo.unclaim_gifts_between(db, user_a_id, user_b_id)
    repo.delete_shares_between(db, user_a_id, user_b_id)
    repo.delete_collection_items_between(db, user_a_id, user_b_id)
