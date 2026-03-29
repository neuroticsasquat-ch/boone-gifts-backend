import sqlalchemy

import pytest

from app.models.connection import Connection
from app.models.user import User


def test_create_connection(db):
    user_a = User(email="usera@test.com", name="User A", password_hash="h")
    user_b = User(email="userb@test.com", name="User B", password_hash="h")
    db.add_all([user_a, user_b])
    db.flush()

    connection = Connection(
        requester_id=user_a.id,
        addressee_id=user_b.id,
    )
    db.add(connection)
    db.flush()

    assert connection.id is not None
    assert connection.requester_id == user_a.id
    assert connection.addressee_id == user_b.id
    assert connection.status == "pending"
    assert connection.created_at is not None
    assert connection.accepted_at is None


def test_accept_connection(db):
    user_a = User(email="usera2@test.com", name="User A", password_hash="h")
    user_b = User(email="userb2@test.com", name="User B", password_hash="h")
    db.add_all([user_a, user_b])
    db.flush()

    connection = Connection(
        requester_id=user_a.id,
        addressee_id=user_b.id,
    )
    db.add(connection)
    db.flush()

    assert connection.status == "pending"

    connection.status = "accepted"
    db.flush()

    assert connection.status == "accepted"


def test_connection_unique_constraint(db):
    user_a = User(email="usera3@test.com", name="User A", password_hash="h")
    user_b = User(email="userb3@test.com", name="User B", password_hash="h")
    db.add_all([user_a, user_b])
    db.flush()

    conn1 = Connection(requester_id=user_a.id, addressee_id=user_b.id)
    db.add(conn1)
    db.flush()

    conn2 = Connection(requester_id=user_a.id, addressee_id=user_b.id)
    db.add(conn2)

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.flush()
