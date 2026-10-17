#!/bin/sh
set -e

alembic upgrade head

if [ -n "$SEED_ADMIN_EMAIL" ] && [ -n "$SEED_ADMIN_NAME" ] && [ -n "$SEED_ADMIN_PASSWORD" ]; then
  python -m app.cli.create_admin \
    --email "$SEED_ADMIN_EMAIL" \
    --name "$SEED_ADMIN_NAME" \
    --password "$SEED_ADMIN_PASSWORD" || true
fi

# Under opentelemetry-instrument (NEU-1599): FastAPI, SQLAlchemy, httpx and logging are
# auto-instrumented, and log records are exported with their trace ids. With more than one
# uvicorn worker, traces and logs still export but metrics do not (OpenTelemetry's
# troubleshooting guide) -- SigNoz derives request rate and latency from the traces.
exec opentelemetry-instrument uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2
