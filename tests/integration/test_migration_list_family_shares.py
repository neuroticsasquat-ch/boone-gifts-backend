"""The list_family_shares backfill (NEU-1202 §2.2, acceptance criterion 1).

Runs the real Alembic migration against a throwaway SQLite file: seeds the schema
at the previous revision with the visibility that existed before that ticket,
upgrades, and checks that every list is still visible to every family its owner
belongs to.

The table itself is gone at head — `b7e2d4f16c93` drops it when sharing re-points
at the occasion (ADR 0002) — so this stops at the revision that does the backfill
rather than running the chain out. The migration still runs on any deploy coming
from a database older than it, which is what keeps this worth testing.
"""
import shutil

import pytest
from sqlalchemy import create_engine, text

from tests.integration.migration_support import alembic as _alembic
from tests.integration.migration_support import build_template

PREVIOUS_REVISION = "13861325bacf"
BACKFILL_REVISION = "c4f2a91d7e30"


def _seed(conn):
    for i, (email, name) in enumerate(
        [("a@t.com", "A"), ("b@t.com", "B")], start=1
    ):
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, role, is_active) "
                "VALUES (:id, :email, :name, 'x', 'member', 1)"
            ),
            {"id": i, "email": email, "name": name},
        )
    conn.execute(
        text(
            "INSERT INTO families (id, name, created_by_id) VALUES "
            "(1, 'F1', 1), (2, 'F2', 1)"
        )
    )
    # A belongs to both families; B to neither.
    conn.execute(
        text(
            "INSERT INTO family_members (family_id, user_id, role) VALUES "
            "(1, 1, 'organizer'), (2, 1, 'organizer')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO lists (id, name, owner_id, is_archived) VALUES "
            "(1, 'A active', 1, 0), (2, 'A archived', 1, 1), (3, 'B list', 2, 0)"
        )
    )



@pytest.fixture(scope="module")
def _template(tmp_path_factory):
    """The schema at the revision before the backfill, seeded with the
    visibility that existed before NEU-1202 — built once for the module."""
    return build_template(tmp_path_factory, PREVIOUS_REVISION, _seed)


@pytest.fixture
def db_path(tmp_path, _template):
    """A private copy of the template, already run through the backfill."""
    path = tmp_path / "migration_test.db"
    shutil.copy(_template, path)
    _alembic("upgrade", BACKFILL_REVISION, path)
    return path


@pytest.fixture
def migrated(db_path):
    engine = create_engine(f"sqlite:///{db_path}")
    yield engine
    engine.dispose()


def _grants(engine):
    with engine.connect() as conn:
        return {
            (row[0], row[1])
            for row in conn.execute(
                text("SELECT list_id, family_id FROM list_family_shares")
            )
        }


def test_backfill_preserves_existing_visibility(migrated):
    # Every list against every family its owner belongs to — archived included,
    # so nothing that was visible the night before the deploy disappears.
    assert _grants(migrated) == {(1, 1), (1, 2), (2, 1), (2, 2)}


def test_backfill_grants_nothing_for_an_owner_in_no_family(migrated):
    assert not [pair for pair in _grants(migrated) if pair[0] == 3]


def test_downgrade_drops_the_table(migrated, db_path):
    _alembic("downgrade", PREVIOUS_REVISION, db_path)
    with migrated.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
    assert "list_family_shares" not in tables
