"""The drop-recipient_has_account migration (NEU-1230).

Runs the real Alembic revision against a throwaway SQLite file. `lists` is
referenced by four other tables, so the column is dropped with a direct DROP
COLUMN rather than batch mode; what needs proving is that the drop leaves every
row's remaining data intact and converts nothing — the `true` rows are beta test
data and become ordinary recipients, not account people (project decision 13).
"""
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text

PREVIOUS_HEAD = "b5e1c7d92a04"
REVISION = "e2b7d4a91c53"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic(command: str, target: str, db_path: Path) -> None:
    env = dict(os.environ, APP_DATABASE_URL=f"sqlite:///{db_path}")
    result = subprocess.run(
        ["alembic", command, target],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _engine(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture
def db_path(tmp_path):
    """A database at the previous head holding all three shapes the column could
    take: a co-resident recipient (`true`), an absent recipient (`false`), and a
    list with no recipient at all (NULL)."""
    path = tmp_path / "drop_recipient_has_account.db"
    _alembic("upgrade", PREVIOUS_HEAD, path)
    engine = _engine(path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, role, is_active) "
                "VALUES (1, 'a@t.com', 'A', 'x', 'member', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO lists (id, name, owner_id, is_archived, recipient_name, "
                "recipient_has_account) VALUES "
                "(1, 'Gran', 1, 0, 'Gran', 1), "
                "(2, 'Beth', 1, 0, 'Beth', 0), "
                "(3, 'Mine', 1, 0, NULL, NULL)"
            )
        )
    engine.dispose()
    return path


def test_upgrade_drops_the_column(db_path):
    _alembic("upgrade", REVISION, db_path)
    columns = {c["name"] for c in inspect(_engine(db_path)).get_columns("lists")}

    assert "recipient_has_account" not in columns
    assert "recipient_name" in columns
    assert "account_person_id" in columns


def test_upgrade_keeps_every_row_and_its_recipient(db_path):
    _alembic("upgrade", REVISION, db_path)
    with _engine(db_path).connect() as conn:
        rows = conn.execute(
            text("SELECT id, recipient_name FROM lists ORDER BY id")
        ).all()

    # The `true` row keeps its name like any other: it is now a recipient in the
    # one remaining sense, not a converted account person.
    assert [tuple(r) for r in rows] == [(1, "Gran"), (2, "Beth"), (3, None)]


def test_upgrade_converts_nothing_into_account_people(db_path):
    _alembic("upgrade", REVISION, db_path)
    with _engine(db_path).connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM account_people")).scalar() == 0
        assert conn.execute(
            text("SELECT COUNT(*) FROM lists WHERE account_person_id IS NOT NULL")
        ).scalar() == 0


def test_downgrade_restores_an_empty_column(db_path):
    _alembic("upgrade", REVISION, db_path)
    _alembic("downgrade", PREVIOUS_HEAD, db_path)
    with _engine(db_path).connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, recipient_name, recipient_has_account "
                "FROM lists ORDER BY id"
            )
        ).all()

    # The rows and their recipients survive; the dropped answers do not, and
    # nothing invents them (§9 — no backfill in either direction).
    assert [tuple(r) for r in rows] == [
        (1, "Gran", None),
        (2, "Beth", None),
        (3, None, None),
    ]
