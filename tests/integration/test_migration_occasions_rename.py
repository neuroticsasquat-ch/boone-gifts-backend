"""The collections → occasions rename (NEU-1226, project spec §7.2).

Runs the real Alembic migration against a throwaway SQLite file: seeds the
schema at the previous head with collections and their items, upgrades, and
checks that every row survived under the new names.
"""
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

PREVIOUS_HEAD = "d8a3f1c05b64"
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


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "migration_test.db"


@pytest.fixture
def seeded(db_path):
    _alembic("upgrade", PREVIOUS_HEAD, db_path)
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, role, is_active) "
                "VALUES (1, 'a@t.com', 'A', 'x', 'member', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO lists (id, name, owner_id, is_archived) VALUES "
                "(1, 'L1', 1, 0), (2, 'L2', 1, 0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO collections (id, owner_id, name, description, is_archived) "
                "VALUES (1, 1, 'Christmas', 'gifts', 0), (2, 1, 'Birthdays', NULL, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO collection_items (id, collection_id, list_id) VALUES "
                "(1, 1, 1), (2, 1, 2), (3, 2, 2)"
            )
        )

    yield engine
    engine.dispose()


@pytest.fixture
def migrated(seeded, db_path):
    _alembic("upgrade", "head", db_path)
    return seeded


def _tables(engine):
    with engine.connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }


def test_tables_are_renamed(migrated):
    tables = _tables(migrated)
    assert {"occasions", "occasion_items"} <= tables
    assert "collections" not in tables
    assert "collection_items" not in tables


def test_occasion_rows_survive_the_rename(migrated):
    with migrated.connect() as conn:
        rows = conn.execute(
            text("SELECT id, owner_id, name, description, is_archived FROM occasions ORDER BY id")
        ).all()
    assert [tuple(row) for row in rows] == [
        (1, 1, "Christmas", "gifts", 0),
        (2, 1, "Birthdays", None, 1),
    ]


def test_timestamps_survive_the_rename(seeded, db_path):
    # The rename is only lossless if the rows come out the far side unchanged,
    # so pin the created_at values from before the upgrade and compare after.
    with seeded.connect() as conn:
        before_occasions = conn.execute(
            text("SELECT id, created_at, updated_at FROM collections ORDER BY id")
        ).all()
        before_items = conn.execute(
            text("SELECT id, created_at FROM collection_items ORDER BY id")
        ).all()

    _alembic("upgrade", "head", db_path)

    with seeded.connect() as conn:
        after_occasions = conn.execute(
            text("SELECT id, created_at, updated_at FROM occasions ORDER BY id")
        ).all()
        after_items = conn.execute(
            text("SELECT id, created_at FROM occasion_items ORDER BY id")
        ).all()

    assert after_occasions == before_occasions
    assert after_items == before_items


def test_item_rows_survive_with_their_ids_and_parents(migrated):
    with migrated.connect() as conn:
        rows = conn.execute(
            text("SELECT id, occasion_id, list_id FROM occasion_items ORDER BY id")
        ).all()
    assert [tuple(row) for row in rows] == [(1, 1, 1), (2, 1, 2), (3, 2, 2)]


def test_no_schema_object_still_says_collection(migrated):
    with migrated.connect() as conn:
        sql = " ".join(
            row[0] or ""
            for row in conn.execute(text("SELECT sql FROM sqlite_master"))
        )
    assert "collection" not in sql.lower()


def test_the_unique_constraint_still_bites(migrated):
    with migrated.begin() as conn:
        # SQLite names the columns rather than the constraint in the error text.
        with pytest.raises(
            IntegrityError,
            match="UNIQUE constraint failed: occasion_items.occasion_id, "
            "occasion_items.list_id",
        ):
            conn.execute(
                text(
                    "INSERT INTO occasion_items (occasion_id, list_id) VALUES (1, 1)"
                )
            )


def test_downgrade_restores_the_old_names_and_rows(migrated, db_path):
    _alembic("downgrade", PREVIOUS_HEAD, db_path)
    tables = _tables(migrated)
    assert {"collections", "collection_items"} <= tables
    assert "occasions" not in tables
    assert "occasion_items" not in tables
    with migrated.connect() as conn:
        occasions = conn.execute(
            text("SELECT id, owner_id, name, description, is_archived FROM collections ORDER BY id")
        ).all()
        items = conn.execute(
            text("SELECT id, collection_id, list_id FROM collection_items ORDER BY id")
        ).all()
    assert [tuple(row) for row in occasions] == [
        (1, 1, "Christmas", "gifts", 0),
        (2, 1, "Birthdays", None, 1),
    ]
    assert [tuple(row) for row in items] == [(1, 1, 1), (2, 1, 2), (3, 2, 2)]
