#!/usr/bin/env bash
set -euo pipefail

VOLUME_NAME="${VOLUME_NAME:-boone-gifts-backend_sqlite-data}"
DB_FILENAME="${DB_FILENAME:-boone_gifts.db}"

: "${STORAGE_BOX_HOST:?STORAGE_BOX_HOST is required}"
: "${STORAGE_BOX_USER:?STORAGE_BOX_USER is required}"
STORAGE_BOX_PATH="${STORAGE_BOX_PATH:-/backups/boone-gifts}"
STORAGE_BOX_PORT="${STORAGE_BOX_PORT:-23}"

TODAY=$(date -u +%Y-%m-%d)
DAY_OF_WEEK=$(date -u +%w)

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting backup"

VOLUME_PATH=$(docker volume inspect --format '{{ .Mountpoint }}' "$VOLUME_NAME")
DB_PATH="$VOLUME_PATH/$DB_FILENAME"

if [ ! -f "$DB_PATH" ]; then
  echo "ERROR: Database not found at $DB_PATH"
  exit 1
fi

echo "Snapshotting $DB_PATH"
sqlite3 "$DB_PATH" ".backup '$TMP_DIR/backup.db'"

echo "Compressing snapshot"
gzip "$TMP_DIR/backup.db"

DAILY_FILE="boone_gifts_${TODAY}.db.gz"

echo "Uploading daily backup: $DAILY_FILE"
rsync -az -e "ssh -p $STORAGE_BOX_PORT -o StrictHostKeyChecking=accept-new" \
  "$TMP_DIR/backup.db.gz" \
  "${STORAGE_BOX_USER}@${STORAGE_BOX_HOST}:${STORAGE_BOX_PATH}/daily/${DAILY_FILE}"

if [ "$DAY_OF_WEEK" -eq 0 ]; then
  echo "Sunday — promoting to weekly: $DAILY_FILE"
  ssh -p "$STORAGE_BOX_PORT" "${STORAGE_BOX_USER}@${STORAGE_BOX_HOST}" \
    "cp ${STORAGE_BOX_PATH}/daily/${DAILY_FILE} ${STORAGE_BOX_PATH}/weekly/${DAILY_FILE}"
fi

echo "Pruning dailies older than 14 days"
ssh -p "$STORAGE_BOX_PORT" "${STORAGE_BOX_USER}@${STORAGE_BOX_HOST}" \
  "find ${STORAGE_BOX_PATH}/daily/ -name '*.db.gz' -mtime +14 -delete" || true

echo "Pruning weeklies older than 56 days"
ssh -p "$STORAGE_BOX_PORT" "${STORAGE_BOX_USER}@${STORAGE_BOX_HOST}" \
  "find ${STORAGE_BOX_PATH}/weekly/ -name '*.db.gz' -mtime +56 -delete" || true

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup complete"
