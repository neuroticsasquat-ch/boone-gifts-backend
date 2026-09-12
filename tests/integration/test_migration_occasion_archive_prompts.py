"""The `occasion_archive_prompts` table (NEU-1294).

Runs the real Alembic revision against a throwaway SQLite file — the only place
schema-level behaviour is actually exercised, since the rest of the suite builds
its tables from the models.

Nothing is backfilled here and nothing could be: no prompt has ever been
dismissed, and inventing a snooze would suppress a nudge the user never saw.
What is worth proving is the shape — the unique constraint that makes the write
an upsert, the two foreign keys that force `delete_family` and the user purge to
clear these rows first, and the `NOT NULL` that keeps "row present, never
dismissed" out of the schema.
"""

import shutil

import pytest
from sqlalchemy import create_engine, event, text

from tests.integration.migration_support import alembic as _alembic
from tests.integration.migration_support import build_template

PREVIOUS_REVISION = "c1f9a7d4e260"
REVISION = "f6b2c9e41a58"

LIVE = "2030-01-01 12:00:00"


def _fk_engine(path):
    """SQLite disables foreign keys by default, and the app turns them on with
    exactly this listener. The FK tests below are meaningless without it."""
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


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
            "INSERT INTO families (id, name, created_by_id) "
            "VALUES (1, 'Boone Family', 1)"
        )
    )
    conn.execute(
        text(
            "INSERT INTO occasions (id, family_id, name, is_archived, "
            "created_by_id) VALUES (1, 1, 'Christmas 2019', 0, 1), "
            "                      (2, 1, 'Christmas 2020', 0, 1)"
        )
    )


@pytest.fixture(scope="module")
def _template(tmp_path_factory):
    """The schema at the previous revision, seeded — built once for the module,
    so the revision chain is replayed once instead of per test."""
    return build_template(tmp_path_factory, PREVIOUS_REVISION, _seed)


@pytest.fixture
def seeded(tmp_path, _template):
    """The schema one revision back, with two users and two occasions of one
    family — enough to say what the unique constraint is keyed on."""
    db_path = tmp_path / "migration_test.db"
    shutil.copy(_template, db_path)
    engine = _fk_engine(db_path)
    yield engine, db_path
    engine.dispose()


def _insert_prompt(engine, **columns) -> None:
    names = ", ".join(columns)
    values = ", ".join(f":{name}" for name in columns)
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO occasion_archive_prompts ({names}) VALUES ({values})"
            ),
            columns,
        )


def test_upgrade_creates_the_table(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with engine.connect() as conn:
        columns = {
            row[1]
            for row in conn.execute(
                text("PRAGMA table_info(occasion_archive_prompts)")
            )
        }
    assert columns == {"id", "user_id", "occasion_id", "dismissed_until"}


def test_one_prompt_per_user_and_occasion(seeded):
    """What makes the write an upsert rather than an insert that can collide: a
    second "not yet" after the first has lapsed extends the snooze."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert_prompt(engine, user_id=1, occasion_id=1, dismissed_until=LIVE)

    with pytest.raises(Exception):
        _insert_prompt(engine, user_id=1, occasion_id=1, dismissed_until=LIVE)


def test_each_user_dismisses_the_same_occasion_separately(seeded):
    """A prompt is per account, so the constraint is on the pair — one member's
    dismissal can never silence another eligible member's."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    _insert_prompt(engine, user_id=1, occasion_id=1, dismissed_until=LIVE)
    _insert_prompt(engine, user_id=2, occasion_id=1, dismissed_until=LIVE)

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM occasion_archive_prompts")
        ).scalar()
    assert count == 2


def test_one_user_may_dismiss_several_occasions(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    _insert_prompt(engine, user_id=1, occasion_id=1, dismissed_until=LIVE)
    _insert_prompt(engine, user_id=1, occasion_id=2, dismissed_until=LIVE)

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM occasion_archive_prompts")
        ).scalar()
    assert count == 2


def test_an_unknown_user_is_refused(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with pytest.raises(Exception):
        _insert_prompt(engine, user_id=999, occasion_id=1, dismissed_until=LIVE)


def test_an_unknown_occasion_is_refused(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with pytest.raises(Exception):
        _insert_prompt(engine, user_id=1, occasion_id=999, dismissed_until=LIVE)


def test_deleting_the_occasion_out_from_under_a_prompt_is_refused(seeded):
    """The foreign key that forces `delete_family` to clear these rows before
    its occasions — it refuses the delete rather than orphaning the row."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert_prompt(engine, user_id=1, occasion_id=1, dismissed_until=LIVE)

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM occasions WHERE id = 1"))


def test_deleting_the_user_out_from_under_a_prompt_is_refused(seeded):
    """The other half, and why `cascade_delete_user` clears by `user_id`."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert_prompt(engine, user_id=1, occasion_id=1, dismissed_until=LIVE)

    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = 1"))


def test_dismissed_until_refuses_null(seeded):
    """A row exists only to record a dismissal, so there is no state in which
    the column is meaningless — and no "row present, never dismissed" for a
    reader to have to branch on."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with pytest.raises(Exception):
        _insert_prompt(engine, user_id=1, occasion_id=1, dismissed_until=None)


def test_downgrade_drops_the_table(seeded):
    """Every snooze is lost and every suppressed nudge returns at the next read
    — the safe direction to fail in."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert_prompt(engine, user_id=1, occasion_id=1, dismissed_until=LIVE)

    _alembic("downgrade", PREVIOUS_REVISION, db_path)

    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
    assert "occasion_archive_prompts" not in tables
