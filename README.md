# Boone Gifts Backend

REST API for Boone Gifts, a gift list and wishlist platform. Users create gift lists, share them with connections, and claim gifts from shared lists.

## Tech Stack

- **Python 3.14** / **FastAPI** / **Uvicorn**
- **SQLAlchemy 2.0** (ORM) + **Alembic** (migrations)
- **SQLite** (file-based database)
- **Pydantic v2** (validation & serialization)
- **PyJWT** + **bcrypt** (auth)
- **Docker Compose** + **Traefik** (reverse proxy)
- **uv** (package management)
- **go-task** (task runner)

## Prerequisites

- Docker Desktop
- [go-task](https://taskfile.dev/)
- A running Traefik instance on the same `proxy` network

## Setup

1. Clone the repo and copy the environment template:

   ```
   cp .env.example .env
   ```

2. Edit `.env` with a JWT secret. The default SQLite paths work for local development.

3. Build and start the container:

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

The API is available at `https://boone-gifts-api.localhost` (via Traefik).

## Development

```
task up              # Build image and start container (runs uvicorn)
task logs            # Follow container logs
task restart         # Restart the container
task test            # Run test suite
task test-file -- <path>  # Run a specific test file
task migrate         # Apply database migrations
task migration -- 'description'  # Generate a new migration
```

### Dependency Management

```
task add -- <package>      # Add a package
task remove -- <package>   # Remove a package
task lock                  # Regenerate lock file
```

## API Overview

### Auth (`/auth`)
- `POST /auth/login` -- Login with email and password
- `POST /auth/register` -- Register with an invite token
- `POST /auth/refresh` -- Refresh an access token

### Users (`/users`) -- admin only
- `GET /users` -- List all users
- `GET /users/{id}` -- Get user details
- `PUT /users/{id}` -- Update a user
- `DELETE /users/{id}` -- Delete a user

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
- `POST /lists` -- Create a gift list
- `GET /lists` -- List your owned and shared lists
- `GET /lists/{id}` -- Get list with gifts
- `PUT /lists/{id}` -- Update a list
- `DELETE /lists/{id}` -- Delete a list

### Gifts (`/lists/{list_id}/gifts`)
- `POST /lists/{id}/gifts` -- Add a gift
- `PUT /lists/{id}/gifts/{gift_id}` -- Update a gift
- `DELETE /lists/{id}/gifts/{gift_id}` -- Delete a gift
- `POST /lists/{id}/gifts/{gift_id}/claim` -- Claim a gift
- `DELETE /lists/{id}/gifts/{gift_id}/claim` -- Unclaim a gift

### Shares (`/lists/{list_id}/shares`)
- `POST /lists/{id}/shares` -- Share a list (requires connection)
- `GET /lists/{id}/shares` -- List shares
- `DELETE /lists/{id}/shares/{user_id}` -- Revoke a share

### Collections (`/collections`)
- `POST /collections` -- Create a collection
- `GET /collections` -- List your collections
- `GET /collections/{id}` -- Get collection with its lists
- `PUT /collections/{id}` -- Update a collection
- `DELETE /collections/{id}` -- Delete a collection
- `POST /collections/{id}/items` -- Add a list to a collection
- `DELETE /collections/{id}/items/{list_id}` -- Remove a list from a collection

### Meta (`/meta`)
- `GET /meta` -- Fetch URL metadata (title, description, price, image)

## Environment Variables

| Variable | Description |
|---|---|
| `APP_DATABASE_URL` | SQLite connection string (e.g., `sqlite:///./data/boone_gifts.db`) |
| `APP_TEST_DATABASE_URL` | SQLite connection string for tests |
| `APP_JWT_SECRET` | Secret key for JWT signing |
| `APP_CORS_ORIGINS` | Allowed CORS origins (JSON array) |

## Testing

```
task test
```

145 tests run against a separate test database. Each test is wrapped in a transaction that rolls back, leaving no persistent data.
