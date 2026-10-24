# Backend Deploy & Operations Runbook

## Architecture

- **Host:** Hetzner VM, managed via Coolify
- **Runtime:** Docker container (FastAPI + Uvicorn, 2 workers)
- **Database:** SQLite on a Docker named volume
- **Auto-deploy:** Push to `main` triggers Coolify redeploy
- **Domain:** `api.boone.gift`
- **Monitoring:** Bugsink (errors, through the Sentry SDK) and SigNoz (traces and logs, through OpenTelemetry)

## Deploy

Push to `main`. Coolify detects the push, builds the image from `Dockerfile.prod`, and replaces the running container. The `start.sh` entrypoint runs `alembic upgrade head` (migrations) before starting Uvicorn.

No manual steps required for a standard deploy.

### Verify a deploy

    curl https://api.boone.gift/health
    # {"status": "healthy"}

Check container status on the VM:

    docker ps --filter "name=app" --format "table {{.Names}}\t{{.Status}}"

Should show `healthy` in the status column.

## Rollback

### Via Coolify

1. Open Coolify dashboard
2. Go to the boone-gifts-backend application
3. Click "Deployments" and select a previous successful deployment
4. Click "Redeploy" on that version

### Via git

    git revert <bad-commit> && git push origin main

This triggers a new deploy with the revert. Preferred over force-pushing.

### If migrations were involved

If the bad deploy included a database migration, reverting the code alone won't undo the schema change. For SQLite, the safest path is restoring from backup (see below).

## Logs

On the VM:

    docker logs <container-name> --tail 100 -f

Find the container name:

    docker ps --filter "name=app" --format "{{.Names}}"

In Coolify: go to the application → Logs tab.

## Container health

The container has a healthcheck hitting `GET /health` every 30 seconds. If the health endpoint fails 3 times in a row, Docker marks the container unhealthy. The `restart: unless-stopped` policy will restart it on crash.

Check health:

    docker inspect <container-name> --format '{{.State.Health.Status}}'

## Restore from backup

See `docs/backup-setup.md` for the full restore procedure. Summary:

1. Download backup from Storage Box
2. Decompress
3. Stop the container
4. Replace the SQLite file in the volume
5. Start the container (migrations run on boot)
6. Verify with `/health`

## Rotate JWT_SECRET

Rotating `APP_JWT_SECRET` invalidates all existing access tokens and refresh tokens immediately. Every logged-in user will be forced to re-authenticate.

Steps:

1. Generate a new secret: `openssl rand -hex 32`
2. Update `APP_JWT_SECRET` in Coolify environment variables
3. Redeploy (Coolify will restart the container with the new value)

**What breaks:** All active sessions are invalidated. Users see a 401 on their next request and must log in again. No data loss.

## Environment variables

Set in Coolify (not in `.env` files):

| Variable | Purpose |
|---|---|
| `APP_JWT_SECRET` | JWT signing key |
| `APP_DATABASE_URL` | SQLite path (default: `sqlite:////data/boone_gifts.db`) |
| `APP_CORS_ORIGINS` | Allowed CORS origins (JSON array) |
| `APP_FRONTEND_URL` | Frontend URL for email links |
| `APP_SENTRY_DSN` | The Bugsink project's DSN — the Sentry SDK reports there. Empty disables error reporting |
| `APP_ENVIRONMENT` | Deployment environment (`production`) — Sentry's `environment` and OTel's `deployment.environment`. Falls back to the older `APP_SENTRY_ENVIRONMENT` when unset |
| `APP_SENTRY_RELEASE` | Optional override for the release tag; unset, it is `SOURCE_COMMIT` (see "Release tagging" below). Leave it unset |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | The SigNoz collector on the internal Docker network. Unset, traces and logs are dropped |
| `OTEL_RESOURCE_ATTRIBUTES` | `service.name=boone-gifts-backend,deployment.environment=production,service.version=$SOURCE_COMMIT` (see "OpenTelemetry" below) |
| `APP_EMAIL_PROVIDER` | `resend` in production (Resend HTTP API); `smtp` or `log` elsewhere |
| `APP_EMAIL_FROM` | Sender address — on the Resend sending subdomain, `Boone Gifts <noreply@mail.boone.gift>` |
| `APP_EMAIL_REPLY_TO` | Reply-To address — set it in Coolify to a mailbox that receives mail (the sender address does not). Empty omits the header |
| `APP_RESEND_API_KEY` | Resend API key for the `boone` team; read only when the provider is `resend` |
| `APP_EMAIL_SMTP_*` | SMTP connection details; only read when the provider is `smtp` |

## Release tagging

Bugsink groups errors by release, and SigNoz labels traces with the same SHA as
`service.version`. We tag each deploy with the Git commit it was built from so a
regression can be tied back to a specific change.

The release is resolved in `app/config.py` (`Settings.release`): `APP_SENTRY_RELEASE`
if it is set, otherwise Coolify's `SOURCE_COMMIT`. The environment is
`APP_ENVIRONMENT` — the same variable OTel's `deployment.environment` reads — with
`APP_SENTRY_ENVIRONMENT` as a fallback. To wire it to the deploy commit:

1. In the Coolify application's **Advanced → Build** settings, set **"Source commit
   availability"** to **Available during build** (Coolify 4.3.23 renamed it from
   "Include SOURCE_COMMIT in build" under General). Without it Coolify sets `SOURCE_COMMIT`
   to the literal `unknown`, and errors are tagged `release=unknown` (passed through
   verbatim, so it matches OTel's `service.version`).
2. Leave `APP_SENTRY_RELEASE` unset (or delete it) in Coolify's **Environment
   Variables** so the release follows `SOURCE_COMMIT`.
3. Confirm `APP_SENTRY_DSN` and `APP_ENVIRONMENT` (`production`) are set in
   Coolify, otherwise error reporting stays disabled / mislabelled.

Performance tracing is enabled at a 10% sample rate (`traces_sample_rate=0.1`)
with explicit FastAPI and SQLAlchemy integrations — no extra config needed.

### Checking what a deploy reports under

    docker exec <api container> python -m app.cli.show_telemetry
    # release=<sha> environment=production sentry=on

(`task show-telemetry` locally.) `release=unknown` or `release=unset` means no
commit reached the app — error tracking still works, it just isn't tied to one.

### Forcing a test error

`POST /debug/raise-test-error` (admin bearer token) raises `TelemetryTestError`
and answers 500. It should arrive as its own issue in the error tracker, tagged
with the release and environment above, and from there reach the alert channel.

    TOKEN=$(curl -s https://api.boone.gift/auth/login \
      -H 'Content-Type: application/json' \
      -d '{"email": "<admin email>", "password": "<password>"}' | jq -r .access_token)
    curl -s -X POST https://api.boone.gift/debug/raise-test-error -H "Authorization: Bearer $TOKEN"

Members get 403 and anonymous callers 401, so the endpoint cannot be used to
flood the tracker.

## OpenTelemetry

`start.sh` runs Uvicorn under `opentelemetry-instrument`, which auto-instruments FastAPI,
SQLAlchemy, httpx and logging and exports over OTLP http/protobuf (pinned in
`Dockerfile.prod`). Nothing about it lives in the repo except that wiring: Coolify sets
`OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_RESOURCE_ATTRIBUTES` (table above; NEU-1619 is the
runbook that sets them). With no endpoint the exporters try `localhost:4318`, fail and log
the failure, and requests are unaffected; `OTEL_SDK_DISABLED=true` switches the SDK off
outright. A literal `$SOURCE_COMMIT` inside a Coolify value is expanded by Coolify (checked
on Sunday Spin, 2026-10-17).

What reaches SigNoz:

- **Traces** — one per request, with its SQL queries and httpx calls beneath it. SQL spans
  need SQLAlchemy below 2.1: the instrumentation's latest release (0.66b1) skips itself on 2.1,
  so `pyproject.toml` holds SQLAlchemy at 2.0 (with a Dependabot ignore) until a release
  supports it. A strict-xfail test in `tests/integration/test_opentelemetry_startup.py` fails
  CI the day one lands, which is the cue to lift the cap.
- **Logs** — application records at WARNING and above, each carrying the trace id of the
  request that wrote it. The app sets no logging level, so the root logger's WARNING decides
  what is exported, and Uvicorn's own loggers do not propagate to the root at all; the
  collector's Docker log receiver still has every line of stdout.
- **Metrics** — not exported: with more than one Uvicorn worker, OpenTelemetry's
  auto-instrumentation exports traces and logs but not metrics. SigNoz derives request rate
  and latency from the traces.

To check a deploy, make a request and find its trace in SigNoz under `boone-gifts-backend`,
with `service.version` = the deployed SHA and `deployment.environment=production`. A healthy
request writes no WARNING, so it has no log line to correlate; a correlated log appears only
when a request logs a failure (a failed outbound email, a LinkPreview fallback).

## Dashboards

- **Coolify:** `https://<coolify-url>` (VM management, deploys, logs)
- **Bugsink:** `https://bugsink.neuroticsasquat.ch` → boone-gifts-backend project
- **SigNoz:** tailnet only → service `boone-gifts-backend`
- **VM SSH:** `ssh <your-vm-alias>`
