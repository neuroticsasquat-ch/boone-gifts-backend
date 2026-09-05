"""The list_family_shares backfill (NEU-1202 §2.2, acceptance criterion 1).

Runs the real Alembic migration against a throwaway SQLite file: seeds the schema
at the previous head with the visibility that existed before this ticket, upgrades,
and checks that every list is still visible to every family its owner belongs to.
"""
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

PREVIOUS_HEAD = "13861325bacf"
REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic(target: str, db_path: Path) -> None:
    import os

    env = dict(os.environ, APP_DATABASE_URL=f"sqlite:///{db_path}")
    result = subprocess.run(
        ["alembic", "upgrade", target],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def migrated(tmp_path):
    db_path = tmp_path / "migration_test.db"
    _alembic(PREVIOUS_HEAD, db_path)
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
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

    _alembic("head", db_path)
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


def test_downgrade_drops_the_table(migrated, tmp_path):
    import os

    db_path = tmp_path / "migration_test.db"
    env = dict(os.environ, APP_DATABASE_URL=f"sqlite:///{db_path}")
    result = subprocess.run(
        ["alembic", "downgrade", PREVIOUS_HEAD],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    with migrated.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
    assert "list_family_shares" not in tables
