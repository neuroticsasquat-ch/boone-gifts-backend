"""scripts.anonymize_db against a real schema, built from the models in a temp file."""

import sqlite3

import bcrypt
import pytest
from sqlalchemy import create_engine

import app.models  # noqa: F401 -- registers every table on Base.metadata
from app.budgets.giftees import key_for_triple
from app.database import Base
from scripts.anonymize_db import LOCAL_PASSWORD, anonymize

EXPIRES = "2030-01-01 00:00:00"


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "prod-copy.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()

    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    db.executemany(
        "INSERT INTO users (id, email, name, password_hash, role, is_active,"
        " is_shared_account) VALUES (?, ?, ?, 'real-hash', ?, 1, 0)",
        [
            (1, "tom@boone.example", "Tom Boone", "admin"),
            (2, "jane@real.example", "Jane Doe", "member"),
        ],
    )
    db.execute(
        "INSERT INTO account_people (id, user_id, name, position)"
        " VALUES (7, 2, 'Little Timmy', 0)"
    )
    db.executemany(
        "INSERT INTO lists (id, name, owner_id, account_person_id, recipient_name,"
        " is_archived) VALUES (?, ?, ?, ?, ?, 0)",
        [
            (1, "Toys", 2, 7, None),
            (2, "For Grandma", 2, None, "Grandma Rose"),
            (3, "Also Grandma", 1, None, "Grandma Rose"),
            (4, "For Uncle", 1, None, "Uncle Bob"),
        ],
    )
    db.execute(
        "INSERT INTO giftee_budgets (id, user_id, giftee_key, owner_id,"
        " account_person_id, recipient_name, amount) VALUES (?, ?, ?, ?, ?, ?, 25)",
        (1, 1, key_for_triple(2, None, "Grandma Rose"), 2, None, "Grandma Rose"),
    )
    db.execute(
        "INSERT INTO invites (token, email, role, expires_at, invited_by_id)"
        " VALUES ('tok', 'new@real.example', 'member', ?, 1)",
        (EXPIRES,),
    )
    db.execute(
        "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)"
        " VALUES (2, 'abc', ?)",
        (EXPIRES,),
    )
    db.commit()
    yield db
    db.close()


def _users(conn):
    return conn.execute(
        "SELECT id, email, name, password_hash FROM users ORDER BY id"
    ).fetchall()


def test_members_lose_email_and_name(conn):
    anonymize(conn)

    _, member = _users(conn)
    assert member[1:3] == ("user-2@anon.local", "User 2")


def test_admins_keep_email_and_name(conn):
    anonymize(conn)

    admin, _ = _users(conn)
    assert admin[1:3] == ("tom@boone.example", "Tom Boone")


def test_every_password_becomes_localdev_admins_included(conn):
    anonymize(conn)

    for *_, password_hash in _users(conn):
        assert bcrypt.checkpw(LOCAL_PASSWORD.encode(), password_hash.encode())


def test_account_people_names_are_replaced(conn):
    anonymize(conn)

    assert conn.execute("SELECT name FROM account_people").fetchall() == [("Person 7",)]


def test_one_recipient_gets_one_pseudonym_everywhere(conn):
    anonymize(conn)

    by_list = dict(conn.execute("SELECT id, recipient_name FROM lists").fetchall())
    assert by_list[2] == by_list[3]
    assert by_list[2] != by_list[4]
    assert by_list[1] is None
    budget_name, budget_key = conn.execute(
        "SELECT recipient_name, giftee_key FROM giftee_budgets"
    ).fetchone()
    assert budget_name == by_list[2]
    assert budget_key == key_for_triple(2, None, by_list[2])


def test_invites_and_reset_tokens_are_emptied(conn):
    anonymize(conn)

    for table in ("invites", "family_invites", "password_reset_tokens"):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_no_real_name_or_address_survives(conn):
    anonymize(conn)

    dump = "\n".join(conn.iterdump())
    for leaked in (
        "Jane Doe",
        "jane@real",
        "Little Timmy",
        "real-hash",
        "Grandma Rose",
        "Uncle Bob",
        "new@real",
    ):
        assert leaked not in dump
