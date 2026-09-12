"""The claim moves off the gift row and onto `claims` (NEU-1268).

Runs the real Alembic revision against a throwaway SQLite file. The backfill is
the point: ADR 0003 preserves every existing claim with its purchase state,
deliberately unlike the family grants the revision before this one dropped. A
dropped grant is re-created in seconds; a dropped claim silently invites two
people to buy the same present.
"""

import shutil

import pytest
from sqlalchemy import create_engine, text

from tests.integration.migration_support import alembic as _alembic
from tests.integration.migration_support import build_template

PREVIOUS_REVISION = "b7e2d4f16c93"
REVISION = "d4c8a1f92b60"


def _seed(conn):
    conn.execute(
        text(
            "INSERT INTO users (id, email, name, password_hash, role, is_active) "
            "VALUES (1, 'a@t.com', 'A', 'x', 'member', 1), "
            "       (2, 'b@t.com', 'B', 'x', 'member', 1)"
        )
    )
    conn.execute(
        text(
            "INSERT INTO lists (id, name, owner_id, is_archived) "
            "VALUES (1, 'A list', 1, 0)"
        )
    )
    conn.execute(
        text(
            "INSERT INTO gifts (id, list_id, name, claimed_by_id, claimed_at, "
            "purchased_at) VALUES "
            "(1, 1, 'A Book', 2, '2026-01-02 03:04:05', NULL), "
            "(2, 1, 'A Kettle', 2, '2026-02-03 04:05:06', "
            "    '2026-03-04 05:06:07'), "
            "(3, 1, 'Unclaimed', NULL, NULL, NULL)"
        )
    )


@pytest.fixture(scope="module")
def _template(tmp_path_factory):
    """The schema at the previous revision, seeded — built once for the
    module, so the revision chain is replayed once instead of per test."""
    return build_template(tmp_path_factory, PREVIOUS_REVISION, _seed)


@pytest.fixture
def seeded(tmp_path, _template):
    """The schema one revision back, holding claims on the gift row: one plain,
    one purchased, and one gift nobody has claimed."""
    db_path = tmp_path / "migration_test.db"
    shutil.copy(_template, db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    yield engine, db_path
    engine.dispose()


def _columns(engine, table):
    with engine.connect() as conn:
        return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}


def test_upgrade_leaves_no_claim_state_on_the_gift_row(seeded):
    """The structural half of ADR 0003: an owner-facing serializer cannot leak
    claim state by forgetting a column, because there is no column."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    columns = _columns(engine, "gifts")
    assert "claimed_by_id" not in columns
    assert "claimed_at" not in columns
    assert "purchased_at" not in columns


def test_upgrade_backfills_every_claim(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT gift_id, user_id FROM claims ORDER BY gift_id")
        ).all()
    # The unclaimed gift gets no row; the two claimed ones keep their claimer.
    assert rows == [(1, 2), (2, 2)]


def test_upgrade_preserves_purchase_state(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with engine.connect() as conn:
        book, kettle = conn.execute(
            text(
                "SELECT claimed_at, purchased_at FROM claims "
                "WHERE gift_id IN (1, 2) ORDER BY gift_id"
            )
        ).all()
    assert book == ("2026-01-02 03:04:05", None)
    assert kettle == ("2026-02-03 04:05:06", "2026-03-04 05:06:07")


def test_backfilled_claims_start_unfiled_and_unpriced(seeded):
    """Filing a claim under an occasion is NEU-1269, and nobody has recorded a
    spend yet — there was no column to record one in."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT occasion_id, amount_paid FROM claims")).all()
    assert rows == [(None, None), (None, None)]


def test_one_claimer_per_gift_is_enforced(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO claims (gift_id, user_id, claimed_at) "
                    "VALUES (1, 1, '2026-04-05 06:07:08')"
                )
            )


def test_downgrade_puts_the_claims_back_on_the_gift_row(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _alembic("downgrade", PREVIOUS_REVISION, db_path)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT claimed_by_id, claimed_at, purchased_at FROM gifts "
                "ORDER BY id"
            )
        ).all()
    assert rows == [
        (2, "2026-01-02 03:04:05", None),
        (2, "2026-02-03 04:05:06", "2026-03-04 05:06:07"),
        (None, None, None),
    ]
    assert "claims" not in {
        row[0]
        for row in engine.connect().execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
    }
