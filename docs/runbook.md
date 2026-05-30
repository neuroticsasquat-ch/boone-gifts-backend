# Backend Deploy & Operations Runbook

## Architecture

- **Host:** Hetzner VM, managed via Coolify
- **Runtime:** Docker container (FastAPI + Uvicorn, 2 workers)
- **Database:** SQLite on a Docker named volume
- **Auto-deploy:** Push to `main` triggers Coolify redeploy
- **Domain:** `api.boone.gift`
- **Monitoring:** Sentry (error tracking)

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
| `APP_SENTRY_DSN` | Sentry DSN for error tracking |
| `APP_SENTRY_ENVIRONMENT` | Sentry environment tag |
| `APP_EMAIL_PROVIDER` | `log` or `smtp` |
| `APP_EMAIL_FROM` | Sender address |
| `APP_EMAIL_SMTP_*` | SMTP connection details |

## Dashboards

- **Coolify:** `https://<coolify-url>` (VM management, deploys, logs)
- **Sentry:** `https://sentry.io` → boone-gifts-backend project
- **VM SSH:** `ssh <your-vm-alias>`
