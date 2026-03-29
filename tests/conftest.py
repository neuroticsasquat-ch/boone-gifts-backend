import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.config import settings
from app.database import Base
from app.dependencies import get_db, create_access_token
from app.main import app
from app.models import User

test_engine = create_engine(
    settings.test_database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(test_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSession(bind=connection)
    yield session
    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db):
    user = User(email="admin@test.com", name="Admin", role="admin", password_hash="x")
    user.set_password("admin123")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def member_user(db):
    user = User(email="member@test.com", name="Member", role="member", password_hash="x")
    user.set_password("member123")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def admin_token(admin_user):
    return create_access_token(admin_user)


@pytest.fixture
def member_token(member_user):
    return create_access_token(member_user)


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def member_headers(member_token):
    return {"Authorization": f"Bearer {member_token}"}


@pytest.fixture
def sample_list(db, member_user):
    from app.models.gift_list import GiftList

    gift_list = GiftList(name="Member's Wishlist", owner_id=member_user.id)
    db.add(gift_list)
    db.flush()
    return gift_list


@pytest.fixture
def shared_list(db, sample_list, admin_user, connection):
    from app.models.list_share import ListShare

    share = ListShare(list_id=sample_list.id, user_id=admin_user.id)
    db.add(share)
    db.flush()
    return sample_list


@pytest.fixture
def connection(db, admin_user, member_user):
    from app.models.connection import Connection

    conn = Connection(
        requester_id=admin_user.id,
        addressee_id=member_user.id,
        status="accepted",
    )
    db.add(conn)
    db.flush()
    return conn


@pytest.fixture
def collection(db, member_user):
    from app.models.collection import Collection

    coll = Collection(name="Christmas 2026", owner_id=member_user.id)
    db.add(coll)
    db.flush()
    return coll


@pytest.fixture
def collection_item(db, collection, sample_list):
    from app.models.collection_item import CollectionItem

    item = CollectionItem(collection_id=collection.id, list_id=sample_list.id)
    db.add(item)
    db.flush()
    return item
