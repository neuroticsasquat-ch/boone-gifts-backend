# Connections Service/Repo Refactoring — Design Spec

## Overview

Refactor the connections domain from a monolithic router into a layered architecture: router (HTTP), service (business logic), and repository (database). This is the reference implementation for the pattern — once validated, the remaining 8 routers will follow the same structure.

## Goals

- Separate HTTP concerns, business logic, and data access into distinct layers
- Make business logic unit-testable without a database
- Establish the service/repo pattern for the rest of the codebase
- Reorganize tests into `tests/unit/` and `tests/integration/`

## Architecture

### Three Layers

**Router** (`app/routers/connections.py`) — HTTP only. Parses request params, calls service, catches domain exceptions, maps to HTTP status codes, returns response. No business logic, no database queries.

**Service** (`app/services/connections.py`) — Business logic. Validates rules (can't self-connect, no duplicates, only addressee can accept, cascade on disconnect). Calls repo for all data access. Raises domain exceptions (not HTTPException).

**Repository** (`app/repos/connections.py`) — Database queries. Find, create, update, delete operations. Takes a SQLAlchemy `Session` and returns model instances or `None`. No business logic, no HTTP concerns.

### Error Handling

Service raises plain Python exceptions. Router maps them to HTTP status codes.

```python
# app/services/exceptions.py
class NotFoundError(Exception): pass
class ForbiddenError(Exception): pass
class ConflictError(Exception): pass
class BadRequestError(Exception): pass
```

Router mapping:
```python
try:
    result = connection_service.create_connection(...)
except BadRequestError as e:
    raise HTTPException(status_code=400, detail=str(e))
except NotFoundError:
    raise HTTPException(status_code=404)
except ForbiddenError:
    raise HTTPException(status_code=403)
except ConflictError:
    raise HTTPException(status_code=409)
```

## Repository: `app/repos/connections.py`

Pure database operations. Each method takes `db: Session` as first argument.

| Method | What it does |
|--------|-------------|
| `find_user_by_id(db, user_id)` | `db.get(User, user_id)` → `User \| None` |
| `find_user_by_email(db, email)` | Query by email → `User \| None` |
| `find_connection_between(db, user_a_id, user_b_id)` | Bidirectional check → `Connection \| None` |
| `find_connection_by_id(db, connection_id)` | `db.get(Connection, connection_id)` → `Connection \| None` |
| `get_accepted_connections(db, user_id)` | All accepted connections for user → `list[Connection]` |
| `get_pending_requests(db, user_id)` | Pending requests where user is addressee → `list[Connection]` |
| `create_connection(db, requester_id, addressee_id)` | Insert + flush → `Connection` |
| `update_connection_accepted(db, connection)` | Set status/accepted_at + flush → `Connection` |
| `delete_connection(db, connection)` | Delete + flush |
| `find_accepted_connection_between(db, user_a_id, user_b_id)` | Like `find_connection_between` but filtered to accepted only → `Connection \| None`. Used by `require_connection` in dependencies.py. |
| `unclaim_gifts_between(db, user_a_id, user_b_id)` | Bulk update: null out claimed_by_id/claimed_at for gifts claimed by either user on the other's lists |
| `delete_shares_between(db, user_a_id, user_b_id)` | Bulk delete: remove all list_shares between both users' lists |
| `delete_collection_items_between(db, user_a_id, user_b_id)` | Bulk delete: remove collection items referencing each other's lists |

## Service: `app/services/connections.py`

Business logic. Each method takes `db: Session` as first argument (passed through from the router's dependency injection). Calls repo methods for data access.

| Method | Logic | Raises |
|--------|-------|--------|
| `create_connection(db, requester_id, target_user_id, target_email)` | Resolve target user (by id or email; `target_user_id` takes precedence when both provided). Validate not self. Check no existing connection. Create via repo. Return connection + target user info. | `BadRequestError` (self), `NotFoundError` (user), `ConflictError` (duplicate) |
| `list_connections(db, user_id)` | Get accepted connections via repo. Build response dicts with other user info. | — |
| `list_requests(db, user_id)` | Get pending requests via repo. Build response dicts with requester info. | — |
| `accept_connection(db, connection_id, user_id)` | Find connection. Validate exists, user is addressee, not already accepted. Update via repo. Return connection + other user info. | `NotFoundError`, `ForbiddenError`, `ConflictError` |
| `delete_connection(db, connection_id, user_id)` | Find connection. Validate exists, user is party. If accepted, cascade disconnect. Delete via repo. | `NotFoundError`, `ForbiddenError` |
| `cascade_disconnect(db, user_a_id, user_b_id)` | Orchestrate: unclaim gifts, delete shares, delete collection items. All via repo. | — |
| `build_connection_response(db, connection, current_user_id)` | Determine other user, fetch their info, return dict matching ConnectionRead schema. | — |

## Router: `app/routers/connections.py` (rewritten)

Thin HTTP wrapper. Each endpoint:
1. Extract params from request/path/query
2. Call service method
3. Catch domain exceptions → map to HTTPException
4. Return response

The router still uses `CurrentUser` and `DbSession` dependencies from `app/dependencies.py`.

## Dependencies Update

`require_connection` in `app/dependencies.py` currently contains a direct database query. It should call `repos.connections.find_accepted_connection_between()` instead, keeping the same interface and HTTPException behavior.

## Test Reorganization

### Directory structure

```
tests/
  unit/
    __init__.py
    services/
      __init__.py
      test_connections.py
  integration/
    __init__.py
    conftest.py            # Moved from tests/conftest.py
    models/                # Moved from tests/models/
      __init__.py
      test_user.py
      test_invite.py
      test_gift_list.py
      test_gift.py
      test_list_share.py
      test_connection.py
      test_collection.py
    routers/               # Moved from tests/routers/
      __init__.py
      test_auth.py
      test_users.py
      test_invites.py
      test_lists.py
      test_gifts.py
      test_list_shares.py
      test_connections.py
      test_collections.py
      test_meta.py
```

The top-level `tests/__init__.py` stays. `tests/conftest.py` moves to `tests/integration/conftest.py`. The old `tests/models/` and `tests/routers/` directories are deleted after moving.

### Unit tests: `tests/unit/services/test_connections.py`

Mock the repo layer using `unittest.mock.patch`. No database, no FastAPI TestClient.

Test cases:
- **create_connection**: self-connect raises BadRequestError, user not found raises NotFoundError, duplicate raises ConflictError, success returns connection response
- **accept_connection**: not found raises NotFoundError, non-addressee raises ForbiddenError, already accepted raises ConflictError, success returns updated connection
- **delete_connection**: not found raises NotFoundError, non-party raises ForbiddenError, pending deletion succeeds without cascade, accepted deletion triggers cascade
- **cascade_disconnect**: calls unclaim_gifts_between, delete_shares_between, delete_collection_items_between in order
- **list_connections**: returns formatted response dicts
- **list_requests**: returns formatted response dicts
- **build_connection_response**: returns correct user info for requester vs addressee

### Integration tests

All existing router and model tests move unchanged to `tests/integration/`. They continue to test the full stack through the database. The only change is their file path.

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/services/__init__.py` | Package marker |
| Create | `app/services/exceptions.py` | Domain exception classes |
| Create | `app/services/connections.py` | Connection business logic |
| Create | `app/repos/__init__.py` | Package marker |
| Create | `app/repos/connections.py` | Connection database queries |
| Rewrite | `app/routers/connections.py` | Thin HTTP wrapper calling service |
| Modify | `app/dependencies.py` | Update `require_connection` to use repo |
| Move | `tests/conftest.py` → `tests/integration/conftest.py` | DB fixtures |
| Move | `tests/models/*` → `tests/integration/models/*` | Model integration tests |
| Move | `tests/routers/*` → `tests/integration/routers/*` | Router integration tests |
| Create | `tests/unit/__init__.py` | Package marker |
| Create | `tests/unit/services/__init__.py` | Package marker |
| Create | `tests/unit/services/test_connections.py` | Service unit tests |

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Only unit tests (fast, no DB)
python -m pytest tests/unit/ -v

# Only integration tests (requires DB)
python -m pytest tests/integration/ -v
```
