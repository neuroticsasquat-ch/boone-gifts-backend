"""The occasions → folders rename (NEU-1258, shopping-lists project spec §11).

Runs the real Alembic migration against a throwaway SQLite file: seeds the
schema at the previous head with occasions and their items, upgrades, and
checks that every row survived under the new names.
"""
import shutil

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.integration.migration_support import alembic as _alembic
from tests.integration.migration_support import build_template

PREVIOUS_HEAD = "e2b7d4a91c53"
REVISION = "c9d4e7a2f180"


def _seed(conn):
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
            "INSERT INTO occasions (id, owner_id, name, description, is_archived) "
            "VALUES (1, 1, 'Christmas', 'gifts', 0), (2, 1, 'Birthdays', NULL, 1)"
        )
    )
    conn.execute(
        text(
            "INSERT INTO occasion_items (id, occasion_id, list_id) VALUES "
            "(1, 1, 1), (2, 1, 2), (3, 2, 2)"
        )
    )


@pytest.fixture(scope="module")
def _template(tmp_path_factory):
    """The schema at the previous head, seeded — built once for the module."""
    return build_template(tmp_path_factory, PREVIOUS_HEAD, _seed)


@pytest.fixture
def db_path(tmp_path, _template):
    """A private copy of the template, for this test to migrate as it likes."""
    path = tmp_path / "migration_test.db"
    shutil.copy(_template, path)
    return path


@pytest.fixture
def seeded(db_path):
    engine = create_engine(f"sqlite:///{db_path}")
    yield engine
    engine.dispose()


@pytest.fixture
def migrated(seeded, db_path):
    _alembic("upgrade", REVISION, db_path)
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
    assert {"folders", "folder_items"} <= tables
    assert "occasions" not in tables
    assert "occasion_items" not in tables


def test_folder_rows_survive_the_rename(migrated):
    with migrated.connect() as conn:
        rows = conn.execute(
            text("SELECT id, owner_id, name, description, is_archived FROM folders ORDER BY id")
        ).all()
    assert [tuple(row) for row in rows] == [
        (1, 1, "Christmas", "gifts", 0),
        (2, 1, "Birthdays", None, 1),
    ]


def test_timestamps_survive_the_rename(seeded, db_path):
    # The rename is only lossless if the rows come out the far side unchanged,
    # so pin the created_at values from before the upgrade and compare after.
    with seeded.connect() as conn:
        before_folders = conn.execute(
            text("SELECT id, created_at, updated_at FROM occasions ORDER BY id")
        ).all()
        before_items = conn.execute(
            text("SELECT id, created_at FROM occasion_items ORDER BY id")
        ).all()

    _alembic("upgrade", REVISION, db_path)

    with seeded.connect() as conn:
        after_folders = conn.execute(
            text("SELECT id, created_at, updated_at FROM folders ORDER BY id")
        ).all()
        after_items = conn.execute(
            text("SELECT id, created_at FROM folder_items ORDER BY id")
        ).all()

    assert after_folders == before_folders
    assert after_items == before_items


def test_item_rows_survive_with_their_ids_and_parents(migrated):
    with migrated.connect() as conn:
        rows = conn.execute(
            text("SELECT id, folder_id, list_id FROM folder_items ORDER BY id")
        ).all()
    assert [tuple(row) for row in rows] == [(1, 1, 1), (2, 1, 2), (3, 2, 2)]


def test_foreign_keys_still_hold(migrated):
    # `folder_items` is rebuilt rather than renamed, so its FKs are written
    # fresh — check they actually point at live rows in `folders` and `lists`.
    with migrated.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []


def test_no_schema_object_still_says_occasion(migrated):
    # The whole point of the revision is to vacate the name for M3's new
    # `occasions` table, so nothing may still be holding it.
    with migrated.connect() as conn:
        sql = " ".join(
            row[0] or ""
            for row in conn.execute(text("SELECT sql FROM sqlite_master"))
        )
    assert "occasion" not in sql.lower()


def test_the_unique_constraint_still_bites(migrated):
    with migrated.begin() as conn:
        # SQLite names the columns rather than the constraint in the error text.
        with pytest.raises(
            IntegrityError,
            match="UNIQUE constraint failed: folder_items.folder_id, "
            "folder_items.list_id",
        ):
            conn.execute(
                text("INSERT INTO folder_items (folder_id, list_id) VALUES (1, 1)")
            )


def test_downgrade_restores_the_old_names_and_rows(migrated, db_path):
    _alembic("downgrade", PREVIOUS_HEAD, db_path)
    tables = _tables(migrated)
    assert {"occasions", "occasion_items"} <= tables
    assert "folders" not in tables
    assert "folder_items" not in tables
    with migrated.connect() as conn:
        occasions = conn.execute(
            text("SELECT id, owner_id, name, description, is_archived FROM occasions ORDER BY id")
        ).all()
        items = conn.execute(
            text("SELECT id, occasion_id, list_id FROM occasion_items ORDER BY id")
        ).all()
    assert [tuple(row) for row in occasions] == [
        (1, 1, "Christmas", "gifts", 0),
        (2, 1, "Birthdays", None, 1),
    ]
    assert [tuple(row) for row in items] == [(1, 1, 1), (2, 1, 2), (3, 2, 2)]
