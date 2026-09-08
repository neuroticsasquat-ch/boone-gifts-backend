# Boone Gifts Backend

REST API for Boone Gifts, a gift list and wishlist platform. Users create gift lists, share them with connections and with families they belong to, and claim gifts from lists shared with them — without the list's owner seeing who claimed what.

For architecture, conventions, and the visibility model, see [`AGENTS.md`](AGENTS.md).

## Tech Stack

- **Python 3.14** / **FastAPI** / **Uvicorn**
- **SQLAlchemy 2.0** (ORM) + **Alembic** (migrations)
- **SQLite** (file-based database)
- **Pydantic v2** (validation & serialization)
- **PyJWT** + **bcrypt** (auth)
- **Docker Compose** (api, web and a Mailpit mail catcher)
- **uv** (package management)
- **go-task** (task runner)

## Prerequisites

- Docker
- [go-task](https://taskfile.dev/)

The compose file lives one directory up and starts the whole stack — this API, the frontend, and Mailpit — so the backend does not run its own compose project.

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

3. Start the stack (from the workspace root, or with `task -d ..` from here):

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

The API is available at `http://localhost:8000` (frontend on `http://localhost:5173`, Mailpit on `http://localhost:8025`). On a remote workspace, use the api and web subdomains it publishes instead, and make sure the web origin is in `APP_CORS_ORIGINS`.

## Development

Stack lifecycle lives in the workspace root Taskfile:

```
task up                  # Start db, mail, api, web
task down                # Stop the stack
task ps                  # Service status
task logs -- api         # Follow one service's logs
task restart -- api      # Restart one service
task rebuild -- api      # Rebuild and recreate one service
task shell -- api        # Shell into a service
```

Repo tasks run inside the api container — from this directory, or prefixed `be:` from the root:

```
task test                        # Run test suite
task test-file -- <path>         # Run a specific test file or test function
task migrate                     # Apply database migrations
task migration -- 'description'  # Generate a new migration
task create-admin                # Create an admin user
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

Creates five `@example.com` users with the list-visibility states a single account can't produce on its own: a directly shared list, a list reaching you only through a family, a list kept for someone with no account, an archived list, a claimed gift, a pending connection request, and a simple-mode user. Purge only deletes rows reachable from those users.

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
- `PUT /auth/profile` -- Update display name and/or simple mode

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
- `GET /connections/{id}/lists` -- Lists that connection has shared with you

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

### Occasions (`/occasions`)
- `POST /occasions` -- Create an occasion
- `GET /occasions` -- List your occasions
- `GET /occasions/for-list/{list_id}` -- Occasions containing a given list
- `GET /occasions/{id}` -- Get occasion with its lists
- `PUT /occasions/{id}` -- Update an occasion
- `DELETE /occasions/{id}` -- Delete an occasion
- `POST /occasions/{id}/items` -- Add a list to an occasion
- `DELETE /occasions/{id}/items/{list_id}` -- Remove a list from an occasion
- `GET /occasions/{id}/shopping-list` -- Everything you've claimed across the occasion

### Meta (`/meta`)
- `GET /meta` -- Fetch URL metadata (title, description, price, image)

### Health
- `GET /health` -- Runs `SELECT 1`; returns 503 when the database is unreachable

## Environment Variables

See [`.env.example`](.env.example) for the full annotated set. The ones you must think about:

| Variable | Description |
|---|---|
| `APP_JWT_SECRET` | Required — the app refuses to start without a real value |
| `APP_DATABASE_URL` | SQLite connection string |
| `APP_TEST_DATABASE_URL` | SQLite connection string for tests |
| `APP_CORS_ORIGINS` | Allowed browser origins, JSON array — the *web* origin, not the API's |
| `APP_FRONTEND_URL` | Base URL used in email links |
| `APP_EMAIL_PROVIDER` | `log` prints to stdout; `smtp` delivers (Mailpit in dev) |

## Testing

```
task test
```

~659 tests run against a separate test database. Each is wrapped in a transaction that rolls back, leaving no persistent data.
