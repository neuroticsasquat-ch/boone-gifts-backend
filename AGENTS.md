# Boone Gifts Backend — Agent Guide

## Quick start
```bash
cp .env.example .env              # then set APP_JWT_SECRET (openssl rand -hex 32)
task up                            # build + start container
task migrate                       # alembic upgrade head
task create-admin                  # interactive prompts
```
API at `https://boone-gifts-api.localhost` (requires Traefik on `proxy` network).

## Commands
All via `go-task` (`task`), every command runs **inside the Docker container**:
- `task up` — `docker compose up --build`
- `task test` — `docker compose exec app pytest tests/ -v`
- `task test-file -- <path>` — run a specific test file/function
- `task migrate` — `alembic upgrade head`
- `task migration -- 'desc'` — `alembic revision --autogenerate`
- `task add -- <pkg>` / `task remove -- <pkg>` — uv add/remove inside container
- `task lock` — `uv lock` inside container
- `task logs` — `docker compose logs -f app`
- `task restart` — `docker compose restart app`

## Architecture
- **Entrypoint**: `main.py` → `app.main.create_app()`. FastAPI factory with CORS, slowapi rate limiter, Sentry init, domain routers, `/health` endpoint (SELECT 1).
- **Package layout**: Each domain (auth, users, invites, lists, gifts, shares, connections, collections, families, family_invites, meta) is a package with `router.py` (thin HTTP), `service.py` (business logic, raises domain exceptions), `repository.py` (queries). Shared exceptions in `app/services/exceptions.py`.
- **ORM**: SQLAlchemy 2.0 mapped columns, `DeclarativeBase`. Pydantic v2 (`model_config`, `model_dump()`, `from_attributes` — never Pydantic v1 patterns).
- **Config**: `app/config.py` via pydantic-settings, `APP_` env prefix, `.env` file.
- **Auth**: JWT HS256 — access token 30min (JSON body), refresh token 7d (HttpOnly cookie `boone_refresh_token`, `Secure`, `SameSite=None`, `Path=/auth`). Registration is invite-only.
- **Rate limiting**: slowapi, configurable via settings. Limiter resets between tests (conftest fixture).

## Critical conventions
- **Router endpoints use `db.flush()`, never `db.commit()`** — the `get_db` dependency commits on success, rolls back on exception. New endpoints must follow this pattern.
- **SQLite FK enforcement**: PRAGMA foreign_keys=ON is set via SQLAlchemy event listener on every connection. Alembic uses `render_as_batch=True`.
- **JWT `sub` claim**: must be a string (`str(user.id)` when encoding, `int(payload["sub"])` when decoding — PyJWT RFC 7519).
- **List visibility**: `can_view_list` in `app/access.py` — owner OR ListShare row OR share a family. Connection alone does NOT grant visibility.
- **Gift responses**: list owners get `GiftOwnerRead` (no claim fields), shared viewers get `GiftRead` (with claim fields).
- **Packages install to `/opt/venv`** (`UV_PROJECT_ENVIRONMENT=/opt/venv`) to avoid bind-mount shadowing. After `task add`, rebuild image with `task up`.

## Debugging CI failures
- **If told a CI/workflow run failed, always investigate via `gh` first** before running anything locally or claiming it's fixed: `gh run list -w CI` to find the failed run, then `gh run view <id> --log-failed` to see what went wrong.
- **Never report something as fixed based on local runs alone** — CI runs in a Docker container and may surface issues local runs miss. Always push/prompt a fresh CI run and confirm it passes before declaring done.

## Pre-commit (not yet installed, but planned)
- Pre-commit will be installed **on the host** (system Python), not inside the container — the hooks themselves delegate via `task` commands to run checks **inside** the Docker container (e.g. `task lint`, `task test`).
- This matters: never install pre-commit or its hooks inside the container; it lives on the host and calls `docker compose exec` under the hood.

## Testing
- ~569 tests: unit tests mock repos, integration tests run against `APP_TEST_DATABASE_URL` SQLite.
- Each integration test is wrapped in a transaction that rolls back (no persistent data).
- Conftest fixtures: `db`, `client`, `admin_user`, `member_user`, `admin_headers`, `member_headers`, `sample_list`, `shared_list`, `connection`, `collection`.
- Rate limiter reset via autouse fixture in conftest.
- CI runs `uv sync --frozen && pytest tests/ -v` with `APP_JWT_SECRET=ci-test-secret`.

## Production
- **Deploy**: Push to `main` triggers Coolify redeploy. `Dockerfile.prod` + `start.sh` (runs migrations, optionally seeds admin). Uvicorn with 2 workers.
- **Domain**: `api.boone.gift`. Health: `curl https://api.boone.gift/health`.
- **Monitoring**: Sentry (DSN optional; env: `production`; release tagged via `SOURCE_COMMIT`).
- **Backup**: `scripts/backup-sqlite.sh` — snapshots SQLite volume, rsyncs to remote Storage Box.

## Environment essentials
| Variable | Notes |
|---|---|
| `APP_JWT_SECRET` | Required — app refuses to start without it or with placeholder |
| `APP_DATABASE_URL` | Default: `sqlite:////data/boone_gifts.db` |
| `APP_EMAIL_PROVIDER` | `log` (stdout) for dev, `smtp` for production |
| `APP_SENTRY_*` | Leave DSN empty to disable Sentry locally |
