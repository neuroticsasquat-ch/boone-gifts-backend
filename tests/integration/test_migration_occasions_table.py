"""The create-occasions migration (NEU-1263).

Runs the real Alembic revision against a throwaway SQLite file. Two things need
proving that the model-built tables cannot show: that the name `occasions` is
genuinely free at this point in the chain — `c9d4e7a2f180` renamed the user's
curated set to `folders` precisely so this table could claim it — and that the
foreign keys and the `is_archived` default hold under `PRAGMA foreign_keys=ON`.
"""
import os
import subprocess
from pathlib import Path

import pytest
import sqlalchemy
from sqlalchemy import create_engine, event, inspect, text

PREVIOUS_HEAD = "f1a6b3c80d27"
REVISION = "a3f8c1e70b52"
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
    """A database at the previous head with one user and one family."""
    path = tmp_path / "occasions_table.db"
    _alembic("upgrade", PREVIOUS_HEAD, path)
    engine = _engine(path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, role, is_active) "
                "VALUES (1, 'organizer@t.com', 'Organizer', 'x', 'member', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO families (id, name, created_by_id) "
                "VALUES (1, 'Boone Family', 1)"
            )
        )
    engine.dispose()
    return path


def test_the_name_occasions_is_free_before_this_revision(db_path):
    """`c9d4e7a2f180` vacated it; the two renames must not share a revision."""
    engine = _engine(db_path)
    assert "occasions" not in inspect(engine).get_table_names()
    assert "folders" in inspect(engine).get_table_names()
    engine.dispose()


def test_upgrade_creates_the_table_with_its_index(db_path):
    _alembic("upgrade", REVISION, db_path)
    engine = _engine(db_path)
    inspector = inspect(engine)

    assert "occasions" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("occasions")}
    assert columns == {
        "id",
        "family_id",
        "name",
        "is_archived",
        "created_by_id",
        "created_at",
        "updated_at",
    }
    indexed = {
        tuple(index["column_names"]) for index in inspector.get_indexes("occasions")
    }
    assert ("family_id",) in indexed
    engine.dispose()


def test_the_table_carries_no_dates(db_path):
    """Deliberate: the occasion's name bounds its period (ADR 0002)."""
    _alembic("upgrade", REVISION, db_path)
    engine = _engine(db_path)

    columns = {c["name"] for c in inspect(engine).get_columns("occasions")}
    assert not {"starts_at", "ends_at", "start_date", "end_date"} & columns
    engine.dispose()


def test_is_archived_defaults_to_false(db_path):
    _alembic("upgrade", REVISION, db_path)
    engine = _engine(db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO occasions (id, family_id, name, created_by_id) "
                "VALUES (1, 1, 'Christmas 2026', 1)"
            )
        )
        assert conn.execute(
            text("SELECT is_archived FROM occasions WHERE id = 1")
        ).scalar_one() == 0
    engine.dispose()


def test_the_foreign_keys_are_enforced(db_path):
    _alembic("upgrade", REVISION, db_path)
    engine = _engine(db_path)
    with engine.begin() as conn:
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO occasions (id, family_id, name, created_by_id) "
                    "VALUES (1, 999, 'Orphan', 1)"
                )
            )
    with engine.begin() as conn:
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO occasions (id, family_id, name, created_by_id) "
                    "VALUES (2, 1, 'Orphan', 999)"
                )
            )
    engine.dispose()


def test_downgrade_drops_the_table(db_path):
    _alembic("upgrade", REVISION, db_path)
    _alembic("downgrade", PREVIOUS_HEAD, db_path)
    engine = _engine(db_path)

    assert "occasions" not in inspect(engine).get_table_names()
    engine.dispose()
