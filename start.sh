#!/bin/sh
set -e

alembic upgrade head

if [ -n "$SEED_ADMIN_EMAIL" ] && [ -n "$SEED_ADMIN_NAME" ] && [ -n "$SEED_ADMIN_PASSWORD" ]; then
  python -m app.cli.create_admin \
    --email "$SEED_ADMIN_EMAIL" \
    --name "$SEED_ADMIN_NAME" \
    --password "$SEED_ADMIN_PASSWORD" || true
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2
