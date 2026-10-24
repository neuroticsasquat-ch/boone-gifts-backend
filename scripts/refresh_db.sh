#!/usr/bin/env bash
#
# Replace the local SQLite database with the latest production daily backup,
# anonymized. Usage: task db:refresh   (or scripts/refresh_db.sh)
#
# The source is the newest boone_gifts_YYYY-MM-DD.db.gz that scripts/backup-sqlite.sh
# uploads to the Hetzner Storage Box each night (docs/backup-setup.md), so prod
# itself is never touched. The copy is migrated and anonymized in the
# boone-gifts-backend container (scripts/anonymize_db.py) *before* it replaces
# data/boone_gifts.db: the file the app reads never holds a production identity,
# and a failure at any step deletes the copy and leaves the current local
# database as it was.
#
# Runs on the host, not in the container: it needs ssh/scp to the Storage Box.
# Everything that needs Python runs in the boone-gifts-backend container, which
# must be up.
#
# Configuration lives in the repo-root .env.local (gitignored), NOT .env, which
# pydantic Settings would reject (unknown keys are an error). See .env.local.example.
#   BACKUP_SSH    required; ssh destination of the Storage Box (an ~/.ssh/config alias)
#   BACKUP_PATH   optional; the dailies directory, default backups/boone-gifts/daily
#   LOCAL_DB      optional; default data/boone_gifts.db (APP_DATABASE_URL in .env)
#   FORCE         optional; 1 skips the confirmation prompt

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)
cd "$REPO_ROOT"

if [[ -f .env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi

BACKUP_PATH="${BACKUP_PATH:-backups/boone-gifts/daily}"
LOCAL_DB="${LOCAL_DB:-data/boone_gifts.db}"
# Inside data/, which is gitignored and bind-mounted at /app/data, so the
# container sees the copy at the same relative path.
WORK_DIR="data/.refresh"
COPY="$WORK_DIR/boone_gifts.db"

if [[ -z "${BACKUP_SSH:-}" ]]; then
  echo "ERROR: BACKUP_SSH is not set. Add it to .env.local (see .env.local.example)." >&2
  exit 1
fi

if ! docker compose ps --status running --services 2>/dev/null | grep -qx boone-gifts-backend; then
  echo "ERROR: the boone-gifts-backend container is not running. Start it first:  task up" >&2
  exit 1
fi

if [[ "${FORCE:-0}" != "1" ]]; then
  echo "This replaces $LOCAL_DB with the latest production backup, anonymized."
  echo "Your current database is kept as $LOCAL_DB.pre-refresh."
  if [[ ! -t 0 ]]; then
    echo "ERROR: refusing to proceed without a terminal. Re-run with FORCE=1." >&2
    exit 1
  fi
  read -r -p "  Type 'refresh' to continue: " reply
  [[ "$reply" == "refresh" ]] || { echo "Aborted."; exit 1; }
fi

# Until the anonymizer has run, the copy holds production PII: on any exit, clean
# or not, it goes.
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "→ Finding the latest daily backup on $BACKUP_SSH:$BACKUP_PATH..."
# The Storage Box's restricted shell has ls; the backup script already relies on
# its ssh (find, cp). ISO dates sort lexically, so the last name is the newest.
LATEST=$(ssh "$BACKUP_SSH" ls -1 "$BACKUP_PATH" \
  | grep -E '^boone_gifts_[0-9]{4}-[0-9]{2}-[0-9]{2}\.db\.gz$' | sort | tail -1 || true)
if [[ -z "$LATEST" ]]; then
  echo "ERROR: no boone_gifts_YYYY-MM-DD.db.gz in $BACKUP_SSH:$BACKUP_PATH." >&2
  exit 1
fi
echo "  $LATEST"

echo "→ Downloading..."
scp -q "$BACKUP_SSH:$BACKUP_PATH/$LATEST" "$COPY.gz"
gunzip "$COPY.gz"

# Before anonymizing, so the anonymizer always sees the schema this checkout's
# models describe, whatever revision prod was on when the backup was taken.
echo "→ Migrating the copy to head..."
docker compose exec -T -e "APP_DATABASE_URL=sqlite:///./$COPY" boone-gifts-backend alembic upgrade head

echo "→ Anonymizing the copy..."
docker compose exec -T boone-gifts-backend python -m scripts.anonymize_db "$COPY"

# Stopped for the swap: closing its connections checkpoints any WAL into the old
# file, so the .pre-refresh copy is complete and no stale -wal is left beside the
# new one.
echo "→ Swapping it in..."
docker compose stop boone-gifts-backend >/dev/null
if [[ -f "$LOCAL_DB" ]]; then
  cp "$LOCAL_DB" "$LOCAL_DB.pre-refresh"
fi
rm -f "$LOCAL_DB-wal" "$LOCAL_DB-shm"
mv "$COPY" "$LOCAL_DB"
docker compose start boone-gifts-backend >/dev/null

echo "✓ $LOCAL_DB refreshed from $LATEST. Log in as an admin or any user-<id>@anon.local, password 'localdev'."
