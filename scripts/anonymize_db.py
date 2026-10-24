"""Strip people out of a copy of the production database before local dev uses it.

    docker compose exec -T api python -m scripts.anonymize_db data/.refresh/boone_gifts.db

`scripts/refresh_db.sh` (`task db:refresh`) runs this on the downloaded backup
*before* it replaces the local database, so the file the app reads never holds a
production identity. It edits the file it is given in place and touches nothing
else; it never goes through `settings.database_url`.

Identity and credentials go; content stays. Lists, gifts, claims, families,
occasions and budgets are the reason to pull production at all, so they survive,
attached to accounts that no longer name anyone:

- `users`: every password becomes `localdev`, admins' included. Everyone but an
  admin (`role = 'admin'`) also gets email `user-{id}@anon.local` and name
  `User {id}`; admins keep theirs, so you log in locally as yourself with the
  password you know. Not `@example.com`: `scripts.seed_dev --purge` deletes
  everything reachable from an `@example.com` user, and would take these with it.
- `account_people.name` becomes `Person {id}` — a real person's name on a shared
  account.
- `recipient_name` (someone a list is kept for who has no account) becomes
  `Recipient {n}`, one `n` per distinct name, the same in `lists` and
  `giftee_budgets`, and `giftee_budgets.giftee_key` is rebuilt from it, because an
  `absent` key carries the name base64-encoded (`app/budgets/giftees.py`).
- `invites`, `family_invites` and `password_reset_tokens` are emptied: each is a
  real address or a still-redeemable token.

Free text — list and gift names, descriptions, family and folder names — is
left as written. It is the content, and it may still mention a first name.

Every rewrite is checked afterwards, and a failed check exits non-zero so the
caller can throw the file away instead of using it.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import bcrypt

from app.budgets.giftees import key_for_triple
from app.models.user import BCRYPT_ROUNDS

LOCAL_PASSWORD = "localdev"

# The role `app/dependencies.py` gates admin routes on. These accounts keep their
# email and name; only their password is reset.
ADMIN_ROLE = "admin"

# Emptied outright. Each row is a real address, a live token, or both.
CLEARED_TABLES = ("invites", "family_invites", "password_reset_tokens")


def anonymize(conn: sqlite3.Connection) -> None:
    """Rewrite identities in place and commit, or raise and roll back."""
    password_hash = bcrypt.hashpw(
        LOCAL_PASSWORD.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode()

    with conn:
        conn.execute("UPDATE users SET password_hash = ?", (password_hash,))
        conn.execute(
            """
            UPDATE users SET
              email = 'user-' || id || '@anon.local',
              name = 'User ' || id
            WHERE role IS NOT ?
            """,
            (ADMIN_ROLE,),
        )
        conn.execute("UPDATE account_people SET name = 'Person ' || id")

        # One pseudonym per distinct name, in a stable order, so the same person
        # reads as the same recipient on every list and budget they appear on.
        names = [
            row[0]
            for row in conn.execute(
                """
                SELECT recipient_name FROM lists WHERE recipient_name IS NOT NULL
                UNION
                SELECT recipient_name FROM giftee_budgets
                 WHERE recipient_name IS NOT NULL
                ORDER BY 1
                """
            )
        ]
        pseudonyms = {name: f"Recipient {n}" for n, name in enumerate(names, 1)}
        conn.executemany(
            "UPDATE lists SET recipient_name = ? WHERE recipient_name = ?",
            [(new, old) for old, new in pseudonyms.items()],
        )
        budgets = conn.execute(
            """
            SELECT id, owner_id, account_person_id, recipient_name
              FROM giftee_budgets
            """
        ).fetchall()
        for budget_id, owner_id, person_id, name in budgets:
            new_name = pseudonyms.get(name) if name is not None else None
            conn.execute(
                """
                UPDATE giftee_budgets SET recipient_name = ?, giftee_key = ?
                 WHERE id = ?
                """,
                (new_name, key_for_triple(owner_id, person_id, new_name), budget_id),
            )

        for table in CLEARED_TABLES:
            conn.execute(f"DELETE FROM {table}")

    check(conn, password_hash)


def check(conn: sqlite3.Connection, password_hash: str) -> None:
    """Fail loudly if any identity survived. Wrong data is not an SQL error, so a
    rewrite that silently matched nothing has to be caught by looking."""
    leftovers = {
        "users not rewritten": conn.execute(
            """
            SELECT count(*) FROM users
             WHERE (email <> 'user-' || id || '@anon.local'
                    OR name <> 'User ' || id)
               AND role IS NOT ?
            """,
            (ADMIN_ROLE,),
        ).fetchone()[0],
        "passwords not reset": conn.execute(
            "SELECT count(*) FROM users WHERE password_hash IS NOT ?",
            (password_hash,),
        ).fetchone()[0],
        "account_people not rewritten": conn.execute(
            "SELECT count(*) FROM account_people WHERE name <> 'Person ' || id"
        ).fetchone()[0],
        "recipient names not rewritten": conn.execute(
            """
            SELECT (SELECT count(*) FROM lists
                     WHERE recipient_name NOT GLOB 'Recipient [0-9]*')
                 + (SELECT count(*) FROM giftee_budgets
                     WHERE recipient_name NOT GLOB 'Recipient [0-9]*')
            """
        ).fetchone()[0],
    }
    for table in CLEARED_TABLES:
        leftovers[f"{table} rows"] = conn.execute(
            f"SELECT count(*) FROM {table}"
        ).fetchone()[0]

    failed = {what: n for what, n in leftovers.items() if n}
    if failed:
        raise RuntimeError(f"anonymization incomplete: {failed}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strip people out of a copy of the production database."
    )
    parser.add_argument("path", type=Path, help="SQLite file to anonymize in place")
    args = parser.parse_args()

    if not args.path.is_file():
        print(f"ERROR: no such file: {args.path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        anonymize(conn)
        users = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        admins = [
            row[0]
            for row in conn.execute(
                "SELECT email FROM users WHERE role = ? ORDER BY id", (ADMIN_ROLE,)
            )
        ]
    except (sqlite3.Error, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"  anonymized {users} users, all with password '{LOCAL_PASSWORD}'")
    print(f"  admins kept by email: {', '.join(admins) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
