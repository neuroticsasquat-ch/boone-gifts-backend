"""The `budgets` table (NEU-1275).

Runs the real Alembic revision against a throwaway SQLite file — the only place
schema-level behaviour is actually exercised, since the rest of the suite builds
its tables from the models.

Nothing is backfilled here and nothing could be: no budget has ever existed, and
inventing one from what somebody has already spent would state a target the user
never set. What is worth proving is the shape — the two unique constraints hold
one budget per scope, and *neither* refuses the NULL that the other scope leaves
behind.
"""
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

PREVIOUS_REVISION = "d4c8a1f92b60"
REVISION = "c1f9a7d4e260"
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
    """The schema one revision back, with two users, a family occasion and a
    folder — the two scopes a budget can hang off."""
    db_path = tmp_path / "migration_test.db"
    _alembic("upgrade", PREVIOUS_REVISION, db_path)
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, role, is_active) "
                "VALUES (1, 'a@t.com', 'A', 'x', 'member', 1), "
                "       (2, 'b@t.com', 'B', 'x', 'member', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO families (id, name, created_by_id) "
                "VALUES (1, 'Boone Family', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO occasions (id, family_id, name, is_archived, "
                "created_by_id) VALUES (1, 1, 'Christmas 2026', 0, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO folders (id, owner_id, name, is_archived) "
                "VALUES (1, 1, 'Gran', 0)"
            )
        )

    yield engine, db_path
    engine.dispose()


def _insert_budget(engine, **columns) -> None:
    names = ", ".join(columns)
    values = ", ".join(f":{name}" for name in columns)
    with engine.begin() as conn:
        conn.execute(
            text(f"INSERT INTO budgets ({names}) VALUES ({values})"), columns
        )


def test_upgrade_creates_the_table(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with engine.connect() as conn:
        columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(budgets)"))
        }
    assert columns == {"id", "user_id", "occasion_id", "folder_id", "amount"}


def test_one_budget_per_user_and_occasion(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert_budget(engine, user_id=1, occasion_id=1, amount=200)

    with pytest.raises(Exception):
        _insert_budget(engine, user_id=1, occasion_id=1, amount=250)


def test_one_budget_per_user_and_folder(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert_budget(engine, user_id=1, folder_id=1, amount=50)

    with pytest.raises(Exception):
        _insert_budget(engine, user_id=1, folder_id=1, amount=60)


def test_each_user_budgets_the_same_occasion_separately(seeded):
    """Every budget is private to the user who set it, so the constraint is on
    the pair — not on the occasion."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    _insert_budget(engine, user_id=1, occasion_id=1, amount=200)
    _insert_budget(engine, user_id=2, occasion_id=1, amount=1000)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM budgets")).scalar() == 2


def test_the_unused_scope_is_null_and_never_collides(seeded):
    """A NULL never collides in a unique index, which is what lets both
    constraints coexist: one user's occasion budgets all leave `folder_id`
    null, and vice versa."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO occasions (id, family_id, name, is_archived, "
                "created_by_id) VALUES (2, 1, \"Gran's 80th\", 0, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO folders (id, owner_id, name, is_archived) "
                "VALUES (2, 1, 'Cousins', 0)"
            )
        )

    _insert_budget(engine, user_id=1, occasion_id=1, amount=200)
    _insert_budget(engine, user_id=1, occasion_id=2, amount=150)
    _insert_budget(engine, user_id=1, folder_id=1, amount=50)
    _insert_budget(engine, user_id=1, folder_id=2, amount=25)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM budgets")).scalar() == 4


def test_downgrade_drops_the_table(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert_budget(engine, user_id=1, occasion_id=1, amount=200)

    _alembic("downgrade", PREVIOUS_REVISION, db_path)

    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
    assert "budgets" not in tables
