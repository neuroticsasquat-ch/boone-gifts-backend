# Connections Service/Repo Refactoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose the monolithic connections router into a layered architecture (router → service → repo) and reorganize tests into unit and integration directories.

**Architecture:** The repo layer handles all database queries. The service layer contains business logic and raises domain exceptions. The router is a thin HTTP wrapper that calls the service and maps exceptions to HTTP status codes. Unit tests mock the repo to test service logic in isolation.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, pytest, unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-29-connections-service-repo-refactor-design.md`

**IMPORTANT:** Do NOT run any git commands that change repo state. Only edit code files and run tests.

**Test commands:**
- All tests: `cd /app/boone-gifts-backend && python -m pytest tests/ -v`
- Unit only: `cd /app/boone-gifts-backend && python -m pytest tests/unit/ -v`
- Integration only: `cd /app/boone-gifts-backend && python -m pytest tests/integration/ -v`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/services/__init__.py` | Package marker |
| Create | `app/services/exceptions.py` | Domain exception classes |
| Create | `app/repos/__init__.py` | Package marker |
| Create | `app/repos/connections.py` | Connection database queries |
| Create | `app/services/connections.py` | Connection business logic |
| Rewrite | `app/routers/connections.py` | Thin HTTP wrapper |
| Modify | `app/dependencies.py` | Update `require_connection` to use repo |
| Move | `tests/conftest.py` → `tests/integration/conftest.py` | DB fixtures |
| Move | `tests/models/*` → `tests/integration/models/*` | Model integration tests |
| Move | `tests/routers/*` → `tests/integration/routers/*` | Router integration tests |
| Create | `tests/unit/__init__.py` | Package marker |
| Create | `tests/unit/services/__init__.py` | Package marker |
| Create | `tests/unit/services/test_connections.py` | Service unit tests |

---

### Task 1: Reorganize test directories

Move existing tests into `tests/integration/` and create the `tests/unit/` structure. No code changes — just file moves and new `__init__.py` files.

**Files:**
- Move: `tests/conftest.py` → `tests/integration/conftest.py`
- Move: `tests/models/` → `tests/integration/models/`
- Move: `tests/routers/` → `tests/integration/routers/`
- Create: `tests/integration/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/services/__init__.py`

- [ ] **Step 1: Create directory structure and move files**

```bash
cd /app/boone-gifts-backend

# Create new directories
mkdir -p tests/integration tests/unit/services

# Create __init__.py files
touch tests/integration/__init__.py
touch tests/unit/__init__.py
touch tests/unit/services/__init__.py

# Move conftest
mv tests/conftest.py tests/integration/conftest.py

# Move test directories
mv tests/models tests/integration/models
mv tests/routers tests/integration/routers
```

- [ ] **Step 2: Verify all existing tests still pass in new locations**

Run: `cd /app/boone-gifts-backend && python -m pytest tests/integration/ -v`

Expected: all 145 tests pass. pytest discovers `conftest.py` in the `tests/integration/` directory and all tests find their fixtures.

- [ ] **Step 3: Verify the full suite command works**

Run: `cd /app/boone-gifts-backend && python -m pytest tests/ -v`

Expected: all 145 tests pass.

---

### Task 2: Create service exceptions and repo layer

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/exceptions.py`
- Create: `app/repos/__init__.py`
- Create: `app/repos/connections.py`

- [ ] **Step 1: Create package markers**

Create `app/services/__init__.py` (empty file):
```python
```

Create `app/repos/__init__.py` (empty file):
```python
```

- [ ] **Step 2: Create service exceptions**

Create `app/services/exceptions.py`:

```python
class NotFoundError(Exception):
    pass


class ForbiddenError(Exception):
    pass


class ConflictError(Exception):
    pass


class BadRequestError(Exception):
    pass
```

- [ ] **Step 3: Create the connections repository**

Create `app/repos/connections.py`:

```python
from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.collection import Collection
from app.models.collection_item import CollectionItem
from app.models.connection import Connection
from app.models.gift import Gift
from app.models.gift_list import GiftList
from app.models.list_share import ListShare
from app.models.user import User


def find_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()


def find_connection_between(db: Session, user_a_id: int, user_b_id: int) -> Connection | None:
    return db.execute(
        select(Connection).where(
            or_(
                (Connection.requester_id == user_a_id)
                & (Connection.addressee_id == user_b_id),
                (Connection.requester_id == user_b_id)
                & (Connection.addressee_id == user_a_id),
            )
        )
    ).scalar_one_or_none()


def find_accepted_connection_between(db: Session, user_a_id: int, user_b_id: int) -> Connection | None:
    return db.execute(
        select(Connection).where(
            Connection.status == "accepted",
            or_(
                (Connection.requester_id == user_a_id)
                & (Connection.addressee_id == user_b_id),
                (Connection.requester_id == user_b_id)
                & (Connection.addressee_id == user_a_id),
            ),
        )
    ).scalar_one_or_none()


def find_connection_by_id(db: Session, connection_id: int) -> Connection | None:
    return db.get(Connection, connection_id)


def get_accepted_connections(db: Session, user_id: int) -> list[Connection]:
    return db.execute(
        select(Connection).where(
            Connection.status == "accepted",
            or_(
                Connection.requester_id == user_id,
                Connection.addressee_id == user_id,
            ),
        )
    ).scalars().all()


def get_pending_requests(db: Session, user_id: int) -> list[Connection]:
    return db.execute(
        select(Connection).where(
            Connection.status == "pending",
            Connection.addressee_id == user_id,
        )
    ).scalars().all()


def create_connection(db: Session, requester_id: int, addressee_id: int) -> Connection:
    connection = Connection(requester_id=requester_id, addressee_id=addressee_id)
    db.add(connection)
    db.flush()
    return connection


def update_connection_accepted(db: Session, connection: Connection) -> Connection:
    connection.status = "accepted"
    connection.accepted_at = datetime.now(timezone.utc)
    db.flush()
    return connection


def delete_connection(db: Session, connection: Connection) -> None:
    db.delete(connection)
    db.flush()


def unclaim_gifts_between(db: Session, user_a_id: int, user_b_id: int) -> None:
    list_ids_a = select(GiftList.id).where(GiftList.owner_id == user_a_id)
    list_ids_b = select(GiftList.id).where(GiftList.owner_id == user_b_id)

    db.execute(
        update(Gift)
        .where(Gift.list_id.in_(list_ids_a), Gift.claimed_by_id == user_b_id)
        .values(claimed_by_id=None, claimed_at=None)
    )
    db.execute(
        update(Gift)
        .where(Gift.list_id.in_(list_ids_b), Gift.claimed_by_id == user_a_id)
        .values(claimed_by_id=None, claimed_at=None)
    )


def delete_shares_between(db: Session, user_a_id: int, user_b_id: int) -> None:
    list_ids_a = select(GiftList.id).where(GiftList.owner_id == user_a_id)
    list_ids_b = select(GiftList.id).where(GiftList.owner_id == user_b_id)

    shares = db.execute(
        select(ListShare).where(
            or_(
                (ListShare.list_id.in_(list_ids_a)) & (ListShare.user_id == user_b_id),
                (ListShare.list_id.in_(list_ids_b)) & (ListShare.user_id == user_a_id),
            )
        )
    ).scalars().all()
    for share in shares:
        db.delete(share)


def delete_collection_items_between(db: Session, user_a_id: int, user_b_id: int) -> None:
    list_ids_a = select(GiftList.id).where(GiftList.owner_id == user_a_id)
    list_ids_b = select(GiftList.id).where(GiftList.owner_id == user_b_id)
    collection_ids_a = select(Collection.id).where(Collection.owner_id == user_a_id)
    collection_ids_b = select(Collection.id).where(Collection.owner_id == user_b_id)

    items = db.execute(
        select(CollectionItem).where(
            or_(
                (CollectionItem.collection_id.in_(collection_ids_a))
                & (CollectionItem.list_id.in_(list_ids_b)),
                (CollectionItem.collection_id.in_(collection_ids_b))
                & (CollectionItem.list_id.in_(list_ids_a)),
            )
        )
    ).scalars().all()
    for item in items:
        db.delete(item)
```

- [ ] **Step 4: Verify existing tests still pass**

Run: `cd /app/boone-gifts-backend && python -m pytest tests/ -v`

Expected: all 145 tests pass (no behavior changed yet).

---

### Task 3: Create the connections service

**Files:**
- Create: `app/services/connections.py`

- [ ] **Step 1: Create the connections service**

Create `app/services/connections.py`:

```python
from sqlalchemy.orm import Session

from app.models.connection import Connection
from app.models.user import User
from app.repos import connections as repo
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)


def build_connection_response(
    db: Session, connection: Connection, current_user_id: int
) -> dict:
    other_id = (
        connection.addressee_id
        if connection.requester_id == current_user_id
        else connection.requester_id
    )
    other_user = repo.find_user_by_id(db, other_id)
    return {
        "id": connection.id,
        "status": connection.status,
        "user": {
            "id": other_user.id,
            "name": other_user.name,
            "email": other_user.email,
        },
        "created_at": connection.created_at,
        "accepted_at": connection.accepted_at,
    }


def create_connection(
    db: Session,
    requester_id: int,
    target_user_id: int | None = None,
    target_email: str | None = None,
) -> dict:
    target: User | None
    if target_user_id is not None:
        target = repo.find_user_by_id(db, target_user_id)
    else:
        target = repo.find_user_by_email(db, target_email)

    if target is None:
        raise NotFoundError("User not found.")

    if target.id == requester_id:
        raise BadRequestError("Cannot connect with yourself.")

    existing = repo.find_connection_between(db, requester_id, target.id)
    if existing is not None:
        raise ConflictError("Connection already exists.")

    connection = repo.create_connection(db, requester_id, target.id)
    return build_connection_response(db, connection, requester_id)


def list_connections(db: Session, user_id: int) -> list[dict]:
    connections = repo.get_accepted_connections(db, user_id)
    return [build_connection_response(db, c, user_id) for c in connections]


def list_requests(db: Session, user_id: int) -> list[dict]:
    connections = repo.get_pending_requests(db, user_id)
    return [build_connection_response(db, c, user_id) for c in connections]


def accept_connection(db: Session, connection_id: int, user_id: int) -> dict:
    connection = repo.find_connection_by_id(db, connection_id)
    if connection is None:
        raise NotFoundError("Connection not found.")
    if connection.addressee_id != user_id:
        raise ForbiddenError("Only the addressee can accept.")
    if connection.status == "accepted":
        raise ConflictError("Already accepted.")

    repo.update_connection_accepted(db, connection)
    return build_connection_response(db, connection, user_id)


def delete_connection(db: Session, connection_id: int, user_id: int) -> None:
    connection = repo.find_connection_by_id(db, connection_id)
    if connection is None:
        raise NotFoundError("Connection not found.")
    if connection.requester_id != user_id and connection.addressee_id != user_id:
        raise ForbiddenError("Not a party to this connection.")

    if connection.status == "accepted":
        cascade_disconnect(db, connection.requester_id, connection.addressee_id)

    repo.delete_connection(db, connection)


def cascade_disconnect(db: Session, user_a_id: int, user_b_id: int) -> None:
    repo.unclaim_gifts_between(db, user_a_id, user_b_id)
    repo.delete_shares_between(db, user_a_id, user_b_id)
    repo.delete_collection_items_between(db, user_a_id, user_b_id)
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd /app/boone-gifts-backend && python -m pytest tests/ -v`

Expected: all 145 tests pass (service exists but isn't wired up yet).

---

### Task 4: Rewrite the connections router and update dependencies

**Files:**
- Rewrite: `app/routers/connections.py`
- Modify: `app/dependencies.py`

- [ ] **Step 1: Rewrite the connections router**

Replace the entire contents of `app/routers/connections.py` with:

```python
from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.schemas.connection import ConnectionCreate, ConnectionRead
from app.services import connections as connection_service
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)

router = APIRouter(prefix="/connections", tags=["connections"])


@router.post("", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
def create_connection(
    request: ConnectionCreate, user: CurrentUser, db: DbSession
) -> dict:
    try:
        return connection_service.create_connection(
            db,
            requester_id=user.id,
            target_user_id=request.user_id,
            target_email=request.email,
        )
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.get("", response_model=list[ConnectionRead])
def list_connections(user: CurrentUser, db: DbSession) -> list[dict]:
    return connection_service.list_connections(db, user.id)


@router.get("/requests", response_model=list[ConnectionRead])
def list_requests(user: CurrentUser, db: DbSession) -> list[dict]:
    return connection_service.list_requests(db, user.id)


@router.post("/{connection_id}/accept", response_model=ConnectionRead)
def accept_connection(
    connection_id: int, user: CurrentUser, db: DbSession
) -> dict:
    try:
        return connection_service.accept_connection(db, connection_id, user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    except ConflictError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: int, user: CurrentUser, db: DbSession
) -> None:
    try:
        connection_service.delete_connection(db, connection_id, user.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    except ForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
```

- [ ] **Step 2: Update `require_connection` in dependencies.py**

In `app/dependencies.py`, replace the `require_connection` function (and the `from app.models.connection import Connection` import above it) with:

```python
from app.repos.connections import find_accepted_connection_between


def require_connection(
    target_user_id: int,
    current_user: User,
    db: Session,
) -> None:
    connection = find_accepted_connection_between(db, current_user.id, target_user_id)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be connected to share a list with this user.",
        )
```

Keep the import of `Connection` if it's used elsewhere in the file. Check first — if only `require_connection` used it, remove it. The `or_` and `select` imports from sqlalchemy may also become unused after this change — remove them only if nothing else in the file uses them.

**IMPORTANT:** Read the file carefully before editing. `or_` is only used by `require_connection`, so it becomes unused after this change — remove it from the sqlalchemy import. `select` is still used by `get_list_for_viewer` — keep it. Remove `from app.models.connection import Connection` entirely (only `require_connection` used it).

- [ ] **Step 3: Run all integration tests**

Run: `cd /app/boone-gifts-backend && python -m pytest tests/integration/ -v`

Expected: all 145 tests pass. The router behavior is identical — same HTTP status codes, same response shapes, same cascade logic. The only change is the internal layering.

---

### Task 5: Write unit tests for the connections service

**Files:**
- Create: `tests/unit/services/test_connections.py`

- [ ] **Step 1: Create the unit test file**

Create `tests/unit/services/test_connections.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.connection import Connection
from app.models.user import User
from app.services import connections as service
from app.services.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)


def _make_user(id: int, name: str = "Test", email: str = "test@test.com") -> MagicMock:
    user = MagicMock(spec=User)
    user.id = id
    user.name = name
    user.email = email
    return user


def _make_connection(
    id: int,
    requester_id: int,
    addressee_id: int,
    status: str = "pending",
    accepted_at: datetime | None = None,
) -> MagicMock:
    conn = MagicMock(spec=Connection)
    conn.id = id
    conn.requester_id = requester_id
    conn.addressee_id = addressee_id
    conn.status = status
    conn.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn.accepted_at = accepted_at
    return conn


REPO = "app.services.connections.repo"


# --- create_connection ---


@patch(f"{REPO}.create_connection")
@patch(f"{REPO}.find_connection_between", return_value=None)
@patch(f"{REPO}.find_user_by_id")
def test_create_connection_by_user_id(mock_find_user, mock_find_conn, mock_create):
    db = MagicMock()
    target = _make_user(2, "Alice", "alice@test.com")
    mock_find_user.side_effect = [target, target]  # once for resolve, once for build_response
    connection = _make_connection(1, 1, 2)
    mock_create.return_value = connection

    result = service.create_connection(db, requester_id=1, target_user_id=2)

    mock_find_user.assert_any_call(db, 2)
    mock_find_conn.assert_called_once_with(db, 1, 2)
    mock_create.assert_called_once_with(db, 1, 2)
    assert result["id"] == 1
    assert result["user"]["name"] == "Alice"


@patch(f"{REPO}.create_connection")
@patch(f"{REPO}.find_connection_between", return_value=None)
@patch(f"{REPO}.find_user_by_email")
@patch(f"{REPO}.find_user_by_id")
def test_create_connection_by_email(mock_find_id, mock_find_email, mock_find_conn, mock_create):
    db = MagicMock()
    target = _make_user(3, "Bob", "bob@test.com")
    mock_find_email.return_value = target
    mock_find_id.return_value = target  # for build_response
    connection = _make_connection(2, 1, 3)
    mock_create.return_value = connection

    result = service.create_connection(db, requester_id=1, target_email="bob@test.com")

    mock_find_email.assert_called_once_with(db, "bob@test.com")
    assert result["user"]["email"] == "bob@test.com"


@patch(f"{REPO}.find_user_by_id", return_value=None)
def test_create_connection_user_not_found(mock_find):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.create_connection(db, requester_id=1, target_user_id=999)


@patch(f"{REPO}.find_user_by_id")
def test_create_connection_self(mock_find):
    db = MagicMock()
    mock_find.return_value = _make_user(1)

    with pytest.raises(BadRequestError, match="yourself"):
        service.create_connection(db, requester_id=1, target_user_id=1)


@patch(f"{REPO}.find_connection_between")
@patch(f"{REPO}.find_user_by_id")
def test_create_connection_duplicate(mock_find_user, mock_find_conn):
    db = MagicMock()
    mock_find_user.return_value = _make_user(2)
    mock_find_conn.return_value = _make_connection(1, 1, 2)

    with pytest.raises(ConflictError):
        service.create_connection(db, requester_id=1, target_user_id=2)


# --- accept_connection ---


@patch(f"{REPO}.find_user_by_id")
@patch(f"{REPO}.update_connection_accepted")
@patch(f"{REPO}.find_connection_by_id")
def test_accept_connection_success(mock_find, mock_update, mock_find_user):
    db = MagicMock()
    conn = _make_connection(1, 10, 20, status="pending")
    mock_find.return_value = conn
    mock_update.return_value = conn
    mock_find_user.return_value = _make_user(10, "Requester", "req@test.com")

    result = service.accept_connection(db, connection_id=1, user_id=20)

    mock_update.assert_called_once_with(db, conn)
    assert result["id"] == 1


@patch(f"{REPO}.find_connection_by_id", return_value=None)
def test_accept_connection_not_found(mock_find):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.accept_connection(db, connection_id=999, user_id=1)


@patch(f"{REPO}.find_connection_by_id")
def test_accept_connection_not_addressee(mock_find):
    db = MagicMock()
    mock_find.return_value = _make_connection(1, 10, 20)

    with pytest.raises(ForbiddenError):
        service.accept_connection(db, connection_id=1, user_id=10)


@patch(f"{REPO}.find_connection_by_id")
def test_accept_connection_already_accepted(mock_find):
    db = MagicMock()
    mock_find.return_value = _make_connection(1, 10, 20, status="accepted")

    with pytest.raises(ConflictError):
        service.accept_connection(db, connection_id=1, user_id=20)


# --- delete_connection ---


@patch(f"{REPO}.delete_connection")
@patch(f"{REPO}.find_connection_by_id")
def test_delete_pending_connection(mock_find, mock_delete):
    db = MagicMock()
    conn = _make_connection(1, 10, 20, status="pending")
    mock_find.return_value = conn

    service.delete_connection(db, connection_id=1, user_id=10)

    mock_delete.assert_called_once_with(db, conn)


@patch(f"{REPO}.delete_collection_items_between")
@patch(f"{REPO}.delete_shares_between")
@patch(f"{REPO}.unclaim_gifts_between")
@patch(f"{REPO}.delete_connection")
@patch(f"{REPO}.find_connection_by_id")
def test_delete_accepted_connection_cascades(
    mock_find, mock_delete, mock_unclaim, mock_shares, mock_items
):
    db = MagicMock()
    conn = _make_connection(1, 10, 20, status="accepted")
    mock_find.return_value = conn

    service.delete_connection(db, connection_id=1, user_id=10)

    mock_unclaim.assert_called_once_with(db, 10, 20)
    mock_shares.assert_called_once_with(db, 10, 20)
    mock_items.assert_called_once_with(db, 10, 20)
    mock_delete.assert_called_once_with(db, conn)


@patch(f"{REPO}.find_connection_by_id", return_value=None)
def test_delete_connection_not_found(mock_find):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.delete_connection(db, connection_id=999, user_id=1)


@patch(f"{REPO}.find_connection_by_id")
def test_delete_connection_not_party(mock_find):
    db = MagicMock()
    mock_find.return_value = _make_connection(1, 10, 20)

    with pytest.raises(ForbiddenError):
        service.delete_connection(db, connection_id=1, user_id=99)


# --- list_connections ---


@patch(f"{REPO}.find_user_by_id")
@patch(f"{REPO}.get_accepted_connections")
def test_list_connections(mock_get, mock_find_user):
    db = MagicMock()
    conn = _make_connection(1, 5, 10, status="accepted")
    mock_get.return_value = [conn]
    mock_find_user.return_value = _make_user(10, "Other", "other@test.com")

    result = service.list_connections(db, user_id=5)

    assert len(result) == 1
    assert result[0]["user"]["name"] == "Other"


@patch(f"{REPO}.get_accepted_connections", return_value=[])
def test_list_connections_empty(mock_get):
    db = MagicMock()
    result = service.list_connections(db, user_id=5)
    assert result == []


# --- list_requests ---


@patch(f"{REPO}.find_user_by_id")
@patch(f"{REPO}.get_pending_requests")
def test_list_requests(mock_get, mock_find_user):
    db = MagicMock()
    conn = _make_connection(1, 10, 5, status="pending")
    mock_get.return_value = [conn]
    mock_find_user.return_value = _make_user(10, "Sender", "sender@test.com")

    result = service.list_requests(db, user_id=5)

    assert len(result) == 1
    assert result[0]["user"]["name"] == "Sender"
    assert result[0]["status"] == "pending"


@patch(f"{REPO}.get_pending_requests", return_value=[])
def test_list_requests_empty(mock_get):
    db = MagicMock()
    result = service.list_requests(db, user_id=5)
    assert result == []


# --- cascade_disconnect ---


@patch(f"{REPO}.delete_collection_items_between")
@patch(f"{REPO}.delete_shares_between")
@patch(f"{REPO}.unclaim_gifts_between")
def test_cascade_disconnect(mock_unclaim, mock_shares, mock_items):
    db = MagicMock()
    service.cascade_disconnect(db, 10, 20)

    mock_unclaim.assert_called_once_with(db, 10, 20)
    mock_shares.assert_called_once_with(db, 10, 20)
    mock_items.assert_called_once_with(db, 10, 20)


# --- build_connection_response ---


@patch(f"{REPO}.find_user_by_id")
def test_build_response_as_requester(mock_find):
    db = MagicMock()
    conn = _make_connection(1, 5, 10, status="accepted")
    mock_find.return_value = _make_user(10, "Addressee", "addr@test.com")

    result = service.build_connection_response(db, conn, current_user_id=5)

    mock_find.assert_called_once_with(db, 10)
    assert result["user"]["name"] == "Addressee"


@patch(f"{REPO}.find_user_by_id")
def test_build_response_as_addressee(mock_find):
    db = MagicMock()
    conn = _make_connection(1, 5, 10, status="accepted")
    mock_find.return_value = _make_user(5, "Requester", "req@test.com")

    result = service.build_connection_response(db, conn, current_user_id=10)

    mock_find.assert_called_once_with(db, 5)
    assert result["user"]["name"] == "Requester"
```

- [ ] **Step 2: Run unit tests**

Run: `cd /app/boone-gifts-backend && python -m pytest tests/unit/ -v`

Expected: all 20 unit tests pass.

- [ ] **Step 3: Run the full test suite**

Run: `cd /app/boone-gifts-backend && python -m pytest tests/ -v`

Expected: all tests pass (145 integration + 20 unit = 165).

---

### Task 6: Update documentation

**Files:**
- Modify: `.claude/CLAUDE.md`

- [ ] **Step 1: Update backend CLAUDE.md**

In `.claude/CLAUDE.md`, make these changes:

1. In the **Project Structure**, add the new directories after the `routers/` section:

```
  services/
    __init__.py
    exceptions.py    # Domain exceptions (NotFoundError, ForbiddenError, ConflictError, BadRequestError)
    connections.py   # Connection business logic (create, accept, delete, cascade disconnect)
  repos/
    __init__.py
    connections.py   # Connection database queries (find, create, update, delete, cascade operations)
```

2. In the **Testing** section, update the test count and add the test structure note:

```
- 165 tests: 20 unit + 145 integration
- Unit tests (`tests/unit/`) mock the repo layer and test service logic in isolation
- Integration tests (`tests/integration/`) run against the SQLite test database
- Each integration test wrapped in a transaction that rolls back (no persistent test data)
```

3. In the **Key Design Decisions** section, add:

```
- **Router → Service → Repo layering** — routers handle HTTP concerns only, services contain business logic and raise domain exceptions, repos handle all database queries. This pattern is implemented for connections and will be extended to other domains.
```

- [ ] **Step 2: Verify all tests pass one final time**

Run: `cd /app/boone-gifts-backend && python -m pytest tests/ -v`

Expected: all 165 tests pass.
