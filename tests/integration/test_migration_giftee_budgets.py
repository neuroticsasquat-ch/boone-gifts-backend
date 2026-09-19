"""The `giftee_budgets` table (NEU-1326).

Runs the real Alembic revision against a throwaway SQLite file — the only place
schema-level behaviour is actually exercised, since the rest of the suite builds
its tables from the models.

Nothing is backfilled and nothing could be: no giftee budget has ever existed,
and splitting an overall across people would state targets the user never set.
What is worth proving is the shape — one row per `(user, scope, key)`, the
NULL of the unused scope never colliding, and the foreign keys the cascades
lean on being real.
"""

import shutil

import pytest
from sqlalchemy import create_engine, event, text

from tests.integration.migration_support import alembic as _alembic
from tests.integration.migration_support import build_template

PREVIOUS_REVISION = "f6b2c9e41a58"
REVISION = "b3e8d1c7a925"


def _seed(conn):
    conn.execute(
        text(
            "INSERT INTO users (id, email, name, password_hash, role, is_active) "
            "VALUES (1, 'a@t.com', 'A', 'x', 'member', 1), "
            "       (2, 'b@t.com', 'B', 'x', 'member', 1)"
        )
    )
    conn.execute(
        text("INSERT INTO families (id, name, created_by_id) VALUES (1, 'Boone Family', 1)")
    )
    conn.execute(
        text(
            "INSERT INTO occasions (id, family_id, name, is_archived, "
            "created_by_id) VALUES (1, 1, 'Christmas 2026', 0, 1)"
        )
    )
    conn.execute(
        text("INSERT INTO folders (id, owner_id, name, is_archived) VALUES (1, 1, 'Gran', 0)")
    )
    conn.execute(
        text(
            "INSERT INTO account_people (id, user_id, name, position) "
            "VALUES (1, 2, 'Gran', 0)"
        )
    )


@pytest.fixture(scope="module")
def _template(tmp_path_factory):
    return build_template(tmp_path_factory, PREVIOUS_REVISION, _seed)


@pytest.fixture
def seeded(tmp_path, _template):
    """The schema one revision back, with two users, an occasion, a folder and
    an account person — every foreign key a giftee budget can hold."""
    db_path = tmp_path / "migration_test.db"
    shutil.copy(_template, db_path)
    engine = create_engine(f"sqlite:///{db_path}")

    # The cascades rely on these keys being enforced, so the test engine turns
    # them on the way the app's engine does.
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    yield engine, db_path
    engine.dispose()


def _insert(engine, **columns) -> None:
    columns.setdefault("owner_id", 2)
    columns.setdefault("amount", 100)
    names = ", ".join(columns)
    values = ", ".join(f":{name}" for name in columns)
    with engine.begin() as conn:
        conn.execute(
            text(f"INSERT INTO giftee_budgets ({names}) VALUES ({values})"), columns
        )


def test_upgrade_creates_the_table(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with engine.connect() as conn:
        columns = {
            row[1] for row in conn.execute(text("PRAGMA table_info(giftee_budgets)"))
        }
    assert columns == {
        "id",
        "user_id",
        "occasion_id",
        "folder_id",
        "giftee_key",
        "owner_id",
        "account_person_id",
        "recipient_name",
        "amount",
    }


def test_one_row_per_user_occasion_and_key(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert(engine, user_id=1, occasion_id=1, giftee_key="owner:2")

    with pytest.raises(Exception):
        _insert(engine, user_id=1, occasion_id=1, giftee_key="owner:2", amount=150)


def test_one_row_per_user_folder_and_key(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert(engine, user_id=1, folder_id=1, giftee_key="owner:2")

    with pytest.raises(Exception):
        _insert(engine, user_id=1, folder_id=1, giftee_key="owner:2", amount=150)


def test_each_user_and_each_giftee_is_a_separate_row(seeded):
    """The constraint is on the triple `(user, scope, key)` — a second user
    budgeting the same giftee, or the same user budgeting a second giftee in
    the same scope, are both fine, and the unused scope's NULL never collides."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    _insert(engine, user_id=1, occasion_id=1, giftee_key="owner:2")
    _insert(engine, user_id=2, occasion_id=1, giftee_key="owner:2")
    _insert(engine, user_id=1, occasion_id=1, giftee_key="person:1", account_person_id=1)
    _insert(engine, user_id=1, folder_id=1, giftee_key="owner:2")

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM giftee_budgets")).scalar() == 4


def test_the_foreign_keys_are_enforced(seeded):
    """`account_person_id` and `owner_id` are real keys, not annotations — that
    is what makes a forgotten cascade fail loudly instead of leaving an orphan
    that no query can resolve a name for."""
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)

    with pytest.raises(Exception):
        _insert(engine, user_id=1, occasion_id=1, giftee_key="person:999", account_person_id=999)
    with pytest.raises(Exception):
        _insert(engine, user_id=1, occasion_id=1, giftee_key="owner:999", owner_id=999)


def test_downgrade_drops_the_table(seeded):
    engine, db_path = seeded
    _alembic("upgrade", REVISION, db_path)
    _insert(engine, user_id=1, occasion_id=1, giftee_key="owner:2")

    _alembic("downgrade", PREVIOUS_REVISION, db_path)

    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert "giftee_budgets" not in tables
    assert "budgets" in tables
