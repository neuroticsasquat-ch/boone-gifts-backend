"""Shared machinery for the `test_migration_*.py` suites.

These are the only tests that run the real Alembic revisions rather than
building tables from the models, so they are the only place schema-level
behaviour — backfills, foreign keys, downgrades — is actually exercised. That
makes them worth their cost, but not worth paying that cost once per test.

Two things live here:

* `alembic()`, which runs a revision **in this process** rather than shelling
  out to the `alembic` CLI. The CLI has to start an interpreter and import
  SQLAlchemy, Alembic and the whole `app` package before it can apply a single
  revision — about 0.9s of the 1.7s a call used to take, paid on every call of
  every test.
* `build_template()`, which replays the chain to a revision and seeds it **once
  per module**, so each test copies a prepared file instead of rebuilding it.

Neither changes what is under test: every test still gets its own throwaway
SQLite file, built by the same revisions, and still runs its own upgrade or
downgrade against it.
"""
from collections.abc import Callable
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine

from alembic import command
from app.config import settings

REPO_ROOT = Path(__file__).resolve().parents[2]

# Built without pointing at `alembic.ini`, deliberately. Everything the ini
# configures beyond `script_location` is Python logging, and `alembic/env.py`
# applies it with `fileConfig(config.config_file_name)` — which reconfigures
# logging process-wide and, by default, disables every logger it did not create.
# Out of a subprocess that was nobody's problem. In this process it tears out
# pytest's `caplog` handler, and the next test that asserts on a log record
# fails somewhere else entirely.
#
# `env.py` already guards on `config.config_file_name is not None`, so leaving
# it unset skips the call: the revisions run, and the suite keeps its logging.
# The database URL is not read from here either — `env.py` takes it from
# `settings.database_url`. One Config object then serves every call.
_CONFIG = Config()
_CONFIG.set_main_option("script_location", str(REPO_ROOT / "alembic"))

_COMMANDS = {"upgrade": command.upgrade, "downgrade": command.downgrade}


def _plain_engine(path: Path) -> Engine:
    return create_engine(f"sqlite:///{path}")


def alembic(command_name: str, target: str, db_path: Path) -> None:
    """Run one Alembic command against `db_path`, in this process.

    `alembic/env.py` resolves the database from `settings.database_url` at the
    moment a migration runs, so pointing that at the throwaway file is all it
    takes to redirect a revision. It is restored afterwards: the setting is
    process-wide, and the rest of the suite reads it too.
    """
    if command_name not in _COMMANDS:
        raise ValueError(
            f"Unknown Alembic command {command_name!r}; "
            f"expected one of {sorted(_COMMANDS)}."
        )
    original = settings.database_url
    settings.database_url = f"sqlite:///{db_path}"
    try:
        _COMMANDS[command_name](_CONFIG, target)
    finally:
        settings.database_url = original


def build_template(
    tmp_path_factory,
    revision: str,
    seed: Callable[[Connection], None],
    engine_factory: Callable[[Path], Engine] | None = None,
) -> Path:
    """Build a database at `revision`, seed it, and return the file.

    Call it from a **module-scoped** fixture: replaying the revision chain is
    the expensive half of these tests, and every test in a module replays the
    same one. Tests take a copy of the result rather than sharing it, so each
    still gets a private file it is free to migrate and mutate.
    """
    path = tmp_path_factory.mktemp("alembic-template") / "seeded.db"
    alembic("upgrade", revision, path)
    # Some suites seed through an engine that turns SQLite's foreign keys on, so
    # that bad seed data fails here rather than surviving into a test. Honour
    # that where they pass it: it is part of what the seed is asserting.
    engine = (engine_factory or _plain_engine)(path)
    try:
        with engine.begin() as conn:
            seed(conn)
    finally:
        engine.dispose()
    return path
