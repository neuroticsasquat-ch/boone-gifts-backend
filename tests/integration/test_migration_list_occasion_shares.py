"""Sharing re-points at the occasion: `list_occasion_shares` in, and
`list_family_shares` out with no backfill (NEU-1265).

Runs the real Alembic revision against a throwaway SQLite file. The dropped
grants are the point, not an oversight — ADR 0002 accepts that every existing
family grant goes and owners re-share, because inventing an occasion per family
would seed every family with a name nobody chose.
"""
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

PREVIOUS_REVISION = "a3f8c1e70b52"
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
def seeded(tmp_path):
    """The schema one revision back, holding a family grant and an occasion."""
    db_path = tmp_path / "migration_test.db"
    _alembic("upgrade", PREVIOUS_REVISION, db_path)
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, role, is_active) "
                "VALUES (1, 'a@t.com', 'A', 'x', 'member', 1)"
            )
        )
        conn.execute(
            text("INSERT INTO families (id, name, created_by_id) VALUES (1, 'F1', 1)")
        )
        conn.execute(
            text(
                "INSERT INTO family_members (family_id, user_id, role) "
                "VALUES (1, 1, 'organizer')"
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
                "INSERT INTO occasions (id, family_id, name, is_archived, created_by_id) "
                "VALUES (1, 1, 'Christmas 2026', 0, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO list_family_shares (list_id, family_id) VALUES (1, 1)"
            )
        )

    yield engine, db_path
    engine.dispose()


def _tables(engine):
    with engine.connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }


def test_upgrade_drops_list_family_shares(seeded):
    engine, db_path = seeded
    _alembic("upgrade", "head", db_path)

    assert "list_family_shares" not in _tables(engine)


def test_upgrade_creates_an_empty_list_occasion_shares(seeded):
    """No backfill: every existing family grant goes, and owners re-share."""
    engine, db_path = seeded
    _alembic("upgrade", "head", db_path)

    assert "list_occasion_shares" in _tables(engine)
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM list_occasion_shares")
        ).scalar()
    assert count == 0


def test_the_new_table_takes_a_share_and_rejects_a_duplicate(seeded):
    engine, db_path = seeded
    _alembic("upgrade", "head", db_path)

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO list_occasion_shares (list_id, occasion_id) VALUES (1, 1)"
            )
        )
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO list_occasion_shares (list_id, occasion_id) "
                    "VALUES (1, 1)"
                )
            )


def test_claims_are_untouched_by_the_drop(seeded):
    """The asymmetry ADR 0002 asks for and warns against tidying: grants are
    dropped, claims are preserved. A dropped grant is re-created in seconds; a
    dropped claim silently invites two people to buy the same present."""
    engine, db_path = seeded
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gifts (id, list_id, name, claimed_by_id) "
                "VALUES (1, 1, 'A Book', 1)"
            )
        )

    _alembic("upgrade", "head", db_path)

    with engine.connect() as conn:
        claimed_by = conn.execute(
            text("SELECT claimed_by_id FROM gifts WHERE id = 1")
        ).scalar()
    assert claimed_by == 1


def test_downgrade_restores_an_empty_list_family_shares(seeded):
    engine, db_path = seeded
    _alembic("upgrade", "head", db_path)
    _alembic("downgrade", PREVIOUS_REVISION, db_path)

    tables = _tables(engine)
    assert "list_family_shares" in tables
    assert "list_occasion_shares" not in tables
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM list_family_shares")).scalar()
    assert count == 0
