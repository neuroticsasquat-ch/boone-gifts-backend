# Boone Gifts Backend

REST API for Boone Gifts, a gift list and wishlist platform. Users create gift lists, share them with connections and with families they belong to, and claim gifts from lists shared with them — without the list's owner seeing who claimed what.

For architecture, conventions, and the visibility model, see [`AGENTS.md`](AGENTS.md).

## Tech Stack

- **Python 3.14** / **FastAPI** / **Uvicorn**
- **SQLAlchemy 2.0** (ORM) + **Alembic** (migrations)
- **SQLite** (file-based database)
- **Pydantic v2** (validation & serialization)
- **PyJWT** + **bcrypt** (auth)
- **Docker Compose** (the api container, behind the shared tbc-localdev-infra Traefik)
- **uv** (package management)
- **go-task** (task runner)

## Prerequisites

- Docker
- [go-task](https://taskfile.dev/)
- [pre-commit](https://pre-commit.com) (`brew install pre-commit`)
- [tbc-localdev-infra](https://github.com/tomboone/tbc-localdev-infra) checked out at `~/projects/tbc-localdev-infra` (Traefik, Mailpit and the `proxy` network)

No Python or virtualenv on the host: every task and hook runs in the `api` container. The database is SQLite under `./data`, so the infra's MySQL and Postgres are not used.

## Setup

1. Copy the environment template:

   ```
   cp .env.example .env
   ```

2. Set `APP_JWT_SECRET` in `.env` to a real value. Generate one with:

   ```
   openssl rand -hex 32
   ```

   The app refuses to start with an empty or placeholder secret. The default SQLite paths work for local development.

3. Start the shared infra and the api container:

   ```
   task up
   ```

4. Run database migrations:

   ```
   task migrate
   ```

5. Create the first admin user:

   ```
   task create-admin
   ```

6. Install the git hook (once):

   ```
   pre-commit install
   ```

   It runs pytest inside the `api` container, so the container must be up to commit.

The API is available at `https://boone-gifts-api.localhost` (frontend on `https://boone-gifts.localhost` once its own `task up` has run, Mailpit on `https://mailpit.localhost`).

## Development

```
task up                  # Start the shared infra, then the api container
task down                # Stop the api container (the shared infra keeps running)
task logs                # Follow the api container's logs
task restart             # Restart the api container
task rebuild             # Rebuild the image and recreate the container
task shell               # Shell into the api container
task infra:status        # Shared infra status (also infra:up / infra:down / infra:logs)
```

Every other task runs inside the api container:

```
task test                        # Run test suite
task test-file -- <path>         # Run a specific test file or test function
task migrate                     # Apply database migrations
task migration -- 'description'  # Generate a new migration
task db:refresh                  # Latest prod backup, anonymized, as the local DB
task create-admin                # Create an admin user
task lint                        # ruff check (not yet clean)
task format                      # ruff format (not yet clean)
task typecheck                   # pyright (not yet clean)
```

### Dependency Management

```
task add -- <package>      # Add a package
task remove -- <package>   # Remove a package
task lock                  # Regenerate lock file
```

### Dev fixtures

```
python -m scripts.seed_dev           # inside the api container
python -m scripts.seed_dev --reset   # re-seed
python -m scripts.seed_dev --purge   # remove
```

Creates five `@example.com` users with the list-visibility states a single account can't produce on its own: a directly shared list, a list reaching you only through a family, a list kept for someone with no account, an archived list, a claimed gift, a pending connection request, and a shared account with two people. Purge only deletes rows reachable from those users.

### Production data, anonymized

```
cp .env.local.example .env.local   # once: set BACKUP_SSH to the Storage Box's ssh alias
task db:refresh                    # prompts, then replaces data/boone_gifts.db
```

Downloads the newest nightly backup from the Hetzner Storage Box (`docs/backup-setup.md`), migrates it to head and anonymizes it in the api container, then swaps it in; the previous file is kept as `data/boone_gifts.db.pre-refresh`. Admin accounts keep their email and name, every other user becomes `user-<id>@anon.local` / `User <id>`, and every password is `localdev`. Shared-account people and off-platform recipients get placeholder names; invites and password-reset tokens are dropped. List and gift text is kept as written. The `@anon.local` domain keeps these users out of reach of `seed_dev --purge`.

## API Overview

### Auth (`/auth`)
- `POST /auth/login` -- Login with email and password
- `POST /auth/register` -- Register with an admin or family invite token
- `GET /auth/invite-info` -- Look up an invite token before registering
- `POST /auth/refresh` -- Refresh an access token (rotates the refresh cookie)
- `POST /auth/logout` -- Clear the refresh cookie
- `POST /auth/forgot-password` -- Request a password reset email
- `POST /auth/reset-password` -- Consume a reset token and set a new password
- `POST /auth/change-password` -- Change password while logged in
- `PUT /auth/profile` -- Update display name

### Users (`/users`)
- `GET /users/search?q=` -- Search users by name or email (any signed-in user; used when adding a connection)
- `GET /users` -- List all users *(admin only)*
- `GET /users/{id}` -- Get user details *(admin only)*
- `PUT /users/{id}` -- Update a user *(admin only)*
- `DELETE /users/{id}` -- Delete a user *(admin only)*

### Invites (`/invites`) -- admin only
- `POST /invites` -- Create an invite
- `GET /invites` -- List invites
- `DELETE /invites/{id}` -- Delete an invite

### Connections (`/connections`)
- `POST /connections` -- Send a connection request (by user_id or email)
- `GET /connections` -- List accepted connections
- `GET /connections/requests` -- List pending incoming requests
- `POST /connections/{id}/accept` -- Accept a request
- `DELETE /connections/{id}` -- Remove connection, reject, or cancel request

### Lists (`/lists`)
- `POST /lists` -- Create a gift list (accepts `family_ids` in full mode)
- `GET /lists` -- Your lists; `?filter=owned|shared`, `?archived=true`. `shared` is the one
  scope for lists others made visible to you, direct or via a family; each row carries
  `shared_via`
- `GET /lists/unseen-count` -- Count of newly shared lists you haven't opened
- `GET /lists/{id}` -- Get list with gifts (owner view or viewer view)
- `PUT /lists/{id}` -- Update a list
- `DELETE /lists/{id}` -- Delete a list

### Gifts (`/lists/{list_id}/gifts`)
- `POST /lists/{id}/gifts` -- Add a gift
- `PUT /lists/{id}/gifts/{gift_id}` -- Update a gift
- `DELETE /lists/{id}/gifts/{gift_id}` -- Delete a gift
- `POST` / `DELETE /lists/{id}/gifts/{gift_id}/claim` -- Claim or unclaim
- `POST` / `DELETE /lists/{id}/gifts/{gift_id}/purchase` -- Mark purchased or not

### Shares (`/lists/{list_id}/shares`)
- `POST /lists/{id}/shares` -- Share a list with a connection
- `GET /lists/{id}/shares` -- List shares
- `GET /lists/{id}/shares/users` -- Connections available to share with
- `DELETE /lists/{id}/shares/{user_id}` -- Revoke a share

### Per-family list sharing (`/lists/{list_id}/families`)
- `GET /lists/{id}/families` -- Every family the owner belongs to, each with a `shared` flag
- `PUT /lists/{id}/families/{family_id}` -- Grant the family access
- `DELETE /lists/{id}/families/{family_id}?claims=release|keep` -- Revoke; returns `409` when a member losing access holds a claim and no choice was given

### Families (`/families`)
- `POST /families` -- Create a family (caller becomes organizer)
- `GET /families` -- Families you belong to
- `GET /families/{id}` -- Family detail with members
- `PUT /families/{id}` -- Rename (organizer only)
- `DELETE /families/{id}` -- Delete with cascade cleanup (organizer only)
- `DELETE /families/{id}/members/{user_id}` -- Leave, or remove a member
- `PUT /families/{id}/members/{user_id}/role` -- Promote or demote

### Family invites
- `POST /families/{id}/invites` -- Invite by email (organizer only)
- `GET /families/{id}/invites` -- Pending outgoing invites (organizer only)
- `DELETE /families/{id}/invites/{invite_id}` -- Revoke an invite
- `GET /families/invites` -- Your incoming invites
- `POST /families/invites/{token}/accept` -- Join the family
- `POST /families/invites/{token}/decline` -- Decline

### Folders (`/folders`)
- `POST /folders` -- Create a folder
- `GET /folders` -- List your folders
- `GET /folders/for-list/{list_id}` -- Folders containing a given list
- `GET /folders/{id}` -- Get folder with its lists
- `PUT /folders/{id}` -- Update a folder
- `DELETE /folders/{id}` -- Delete a folder
- `POST /folders/{id}/items` -- Add a list to a folder
- `DELETE /folders/{id}/items/{list_id}` -- Remove a list from a folder
- `GET /folders/{id}/shopping` -- Everything you've claimed across the folder

### Occasions (`/families/{family_id}/occasions`, `/occasions`)
- `GET /occasions` -- Every occasion across every family you belong to, with your own counts
- `GET /families/{family_id}/occasions` -- The family's occasions; any member
- `POST /families/{family_id}/occasions` -- Create one; any member
- `GET /occasions/{id}` -- Get an occasion; any member of its family
- `PUT /occasions/{id}` -- Rename or archive; organizers only
- `GET /occasions/{id}/lists` -- The lists shared to it that you can see
- `GET /occasions/{id}/shopping` -- Everything *you* have claimed under it

### Meta (`/meta`)
- `GET /meta` -- Fetch URL metadata (title, description, price, image)

### Health
- `GET /health` -- Runs `SELECT 1`; returns 503 when the database is unreachable

### Debug (`/debug`) -- admin only
- `POST /debug/raise-test-error` -- Raise a deliberate `TelemetryTestError` (500) to prove errors reach the tracker; see [docs/runbook.md](docs/runbook.md#forcing-a-test-error)

## Environment Variables

See [`.env.example`](.env.example) for the full annotated set. The ones you must think about:

| Variable | Description |
|---|---|
| `APP_JWT_SECRET` | Required — the app refuses to start without a real value |
| `APP_DATABASE_URL` | SQLite connection string |
| `APP_TEST_DATABASE_URL` | SQLite connection string for tests |
| `APP_CORS_ORIGINS` | Allowed browser origins, JSON array — the *web* origin, not the API's |
| `APP_FRONTEND_URL` | Base URL used in email links |
| `APP_EMAIL_PROVIDER` | `log` prints to stdout; `smtp` delivers over SMTP (Mailpit in dev); `resend` delivers through the Resend API (production) |
| `APP_RESEND_API_KEY` | Resend API key, read only when the provider is `resend` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Production only, set in Coolify: the SigNoz collector the server exports traces and logs to |
| `OTEL_RESOURCE_ATTRIBUTES` | Production only, set in Coolify: `service.name=boone-gifts-backend,deployment.environment=production,service.version=$SOURCE_COMMIT` |
| `OTEL_SDK_DISABLED` | `true` in the dev image, so nothing tries to export locally |

The production server runs under `opentelemetry-instrument` (`start.sh`); see `docs/runbook.md` → OpenTelemetry for what reaches SigNoz.

## Testing

```
task test
```

~659 tests run against a separate test database. Each is wrapped in a transaction that rolls back, leaving no persistent data.
