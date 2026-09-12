"""The shared-accounts migration (NEU-1228 §2.1).

Runs the real Alembic revision against a throwaway SQLite file. The migration is
purely additive and backfills nothing, so what needs proving is that existing
rows come through untouched and that `lists.account_person_id` carries a
*genuine* foreign key — it is added with raw DDL, because alembic renders a
column with a ForeignKey as an ALTER TABLE ADD CONSTRAINT that SQLite rejects.
"""
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.integration.migration_support import alembic as _alembic
from tests.integration.migration_support import build_template

PREVIOUS_HEAD = "a7c4e2b91f38"
REVISION = "b5e1c7d92a04"


def _engine(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _seed(conn):
    conn.execute(
        text(
            "INSERT INTO users (id, email, name, password_hash, role, is_active) "
            "VALUES (1, 'a@t.com', 'A', 'x', 'member', 1)"
        )
    )
    conn.execute(
        text(
            "INSERT INTO lists (id, name, owner_id, is_archived, recipient_name, "
            "recipient_has_account) VALUES (1, 'L', 1, 0, 'Beth', 1)"
        )
    )


@pytest.fixture(scope="module")
def _template(tmp_path_factory):
    """The schema at the previous head, seeded — built once for the module,
    so the revision chain is replayed once instead of per test."""
    return build_template(tmp_path_factory, PREVIOUS_HEAD, _seed, _engine)


@pytest.fixture
def db_path(tmp_path, _template):
    """A database at the previous head, holding one user and one list that
    already names a recipient with an account — the row NEU-1230 will deal with,
    and the row this migration must leave completely alone."""
    path = tmp_path / "shared_accounts_migration.db"
    shutil.copy(_template, path)
    return path


def test_upgrade_adds_the_schema(db_path):
    _alembic("upgrade", REVISION, db_path)
    inspector = inspect(_engine(db_path))

    assert "account_people" in inspector.get_table_names()
    assert {c["name"] for c in inspector.get_columns("account_people")} == {
        "id", "user_id", "name", "position", "created_at"
    }
    assert [c["column_names"] for c in inspector.get_unique_constraints("account_people")] == [
        ["user_id", "name"]
    ]
    indexed = {tuple(i["column_names"]) for i in inspector.get_indexes("account_people")}
    assert ("user_id",) in indexed
    assert ("account_person_id",) in {
        tuple(i["column_names"]) for i in inspector.get_indexes("lists")
    }


def test_upgrade_leaves_existing_rows_alone(db_path):
    _alembic("upgrade", REVISION, db_path)
    with _engine(db_path).connect() as conn:
        row = conn.execute(
            text(
                "SELECT is_shared_account FROM users WHERE id = 1"
            )
        ).one()
        assert row[0] == 0
        gift_list = conn.execute(
            text(
                "SELECT recipient_name, recipient_has_account, account_person_id "
                "FROM lists WHERE id = 1"
            )
        ).one()
    # No backfill: the recipient stays exactly as it was, and no label appears.
    assert tuple(gift_list) == ("Beth", 1, None)


def test_account_person_id_is_a_real_foreign_key(db_path):
    _alembic("upgrade", REVISION, db_path)
    engine = _engine(db_path)

    assert any(
        fk["constrained_columns"] == ["account_person_id"]
        and fk["referred_table"] == "account_people"
        for fk in inspect(engine).get_foreign_keys("lists")
    )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO lists (id, name, owner_id, is_archived, "
                    "account_person_id) VALUES (2, 'Ghost', 1, 0, 999)"
                )
            )


def test_foreign_key_refuses_to_orphan_a_label(db_path):
    _alembic("upgrade", REVISION, db_path)
    engine = _engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO account_people (id, user_id, name, position) "
                "VALUES (1, 1, 'Gran', 0)"
            )
        )
        conn.execute(text("UPDATE lists SET recipient_name = NULL, "
                          "recipient_has_account = NULL, account_person_id = 1 "
                          "WHERE id = 1"))

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM account_people WHERE id = 1"))


def test_downgrade_round_trips(db_path):
    _alembic("upgrade", REVISION, db_path)
    _alembic("downgrade", PREVIOUS_HEAD, db_path)
    inspector = inspect(_engine(db_path))

    assert "account_people" not in inspector.get_table_names()
    assert "account_person_id" not in {c["name"] for c in inspector.get_columns("lists")}
    assert "is_shared_account" not in {c["name"] for c in inspector.get_columns("users")}
    # The pre-existing row is still there, unharmed.
    with _engine(db_path).connect() as conn:
        assert conn.execute(text("SELECT recipient_name FROM lists")).scalar() == "Beth"
