"""The drop-simple_mode migration (NEU-1260).

Runs the real Alembic revision against a throwaway SQLite file. `users` is
referenced by many other tables, so both columns go with a direct DROP COLUMN
rather than batch mode (following e2b7d4a91c53); what needs proving is that the
drop leaves every row's remaining data intact and that this revision touches no
existing grant. (A later revision drops the grants wholesale when shares move to
occasions — project spec §12 — but retiring the mode must not pre-empt it.)
"""
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text

PREVIOUS_HEAD = "c9d4e7a2f180"
REVISION = "f1a6b3c80d27"
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
    """A database at the previous head with a simple-mode user and a full-mode
    one, an invite of each kind, and a grant belonging to the simple-mode user —
    the row whose survival is the whole point of the no-backfill decision."""
    path = tmp_path / "drop_simple_mode.db"
    _alembic("upgrade", PREVIOUS_HEAD, path)
    engine = _engine(path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, role, is_active, "
                "simple_mode) VALUES "
                "(1, 'simple@t.com', 'Simple', 'x', 'member', 1, 1), "
                "(2, 'full@t.com', 'Full', 'x', 'member', 1, 0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO families (id, name, created_by_id) VALUES (1, 'Boones', 2)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO family_invites (id, family_id, email, role, simple_mode, "
                "token, invited_by_id, expires_at) VALUES "
                "(1, 1, 'a@t.com', 'member', 1, 'tok-a', 2, '2030-01-01 00:00:00'), "
                "(2, 1, 'b@t.com', 'organizer', 0, 'tok-b', 2, '2030-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO lists (id, name, owner_id, is_archived) "
                "VALUES (1, 'Simple List', 1, 0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO list_family_shares (list_id, family_id) VALUES (1, 1)"
            )
        )
    engine.dispose()
    return path


def test_upgrade_drops_both_columns(db_path):
    _alembic("upgrade", REVISION, db_path)
    inspector = inspect(_engine(db_path))

    user_columns = {c["name"] for c in inspector.get_columns("users")}
    assert "simple_mode" not in user_columns
    # The neighbouring booleans on the same table are untouched.
    assert "is_active" in user_columns
    assert "is_shared_account" in user_columns

    invite_columns = {c["name"] for c in inspector.get_columns("family_invites")}
    assert "simple_mode" not in invite_columns
    assert "role" in invite_columns
    assert "declined_at" in invite_columns


def test_upgrade_keeps_every_row_and_its_remaining_data(db_path):
    _alembic("upgrade", REVISION, db_path)
    with _engine(db_path).connect() as conn:
        users = conn.execute(
            text("SELECT id, email, role, is_active FROM users ORDER BY id")
        ).all()
        invites = conn.execute(
            text("SELECT id, email, role, token FROM family_invites ORDER BY id")
        ).all()

    assert [tuple(r) for r in users] == [
        (1, "simple@t.com", "member", 1),
        (2, "full@t.com", "member", 1),
    ]
    assert [tuple(r) for r in invites] == [
        (1, "a@t.com", "member", "tok-a"),
        (2, "b@t.com", "organizer", "tok-b"),
    ]


def test_upgrade_touches_no_existing_grant(db_path):
    _alembic("upgrade", REVISION, db_path)
    with _engine(db_path).connect() as conn:
        rows = conn.execute(
            text("SELECT list_id, family_id FROM list_family_shares")
        ).all()

    # The simple-mode owner keeps the grant the auto-grant gave them: dropping
    # the column retires the behaviour, it does not un-share anything.
    assert [tuple(r) for r in rows] == [(1, 1)]


def test_downgrade_restores_empty_columns(db_path):
    _alembic("upgrade", REVISION, db_path)
    _alembic("downgrade", PREVIOUS_HEAD, db_path)
    with _engine(db_path).connect() as conn:
        users = conn.execute(
            text("SELECT id, simple_mode FROM users ORDER BY id")
        ).all()
        invites = conn.execute(
            text("SELECT id, simple_mode FROM family_invites ORDER BY id")
        ).all()

    # Every row comes back False — no backfill in either direction, so a
    # downgraded database automatically grants nothing.
    assert [tuple(r) for r in users] == [(1, 0), (2, 0)]
    assert [tuple(r) for r in invites] == [(1, 0), (2, 0)]
