from types import SimpleNamespace
from unittest.mock import patch

from app import access

ACCESS = "app.access"


def _user(user_id):
    return SimpleNamespace(id=user_id)


def _list(list_id, owner_id):
    return SimpleNamespace(id=list_id, owner_id=owner_id)


# ---------------------------------------------------------------------------
# can_view_list  (owner OR share OR shared-family)
# ---------------------------------------------------------------------------


def test_can_view_list_owner_returns_true():
    # Owner short-circuits before any repo/service lookup.
    assert access.can_view_list(None, _user(1), _list(5, owner_id=1)) is True


def test_can_view_list_with_share_returns_true():
    with patch(f"{ACCESS}.find_share", return_value=object()), \
         patch(f"{ACCESS}.users_share_family", return_value=False):
        assert access.can_view_list(None, _user(2), _list(5, owner_id=1)) is True


def test_can_view_list_with_shared_family_returns_true():
    with patch(f"{ACCESS}.find_share", return_value=None), \
         patch(f"{ACCESS}.users_share_family", return_value=True):
        assert access.can_view_list(None, _user(2), _list(5, owner_id=1)) is True


def test_can_view_list_no_access_returns_false():
    with patch(f"{ACCESS}.find_share", return_value=None), \
         patch(f"{ACCESS}.users_share_family", return_value=False):
        assert access.can_view_list(None, _user(2), _list(5, owner_id=1)) is False


def test_can_view_list_connection_only_returns_false():
    # No share, no shared family. A connection may exist, but can_view_list must
    # NOT grant visibility on a connection alone — and must never consult one.
    with patch(f"{ACCESS}.find_share", return_value=None), \
         patch(f"{ACCESS}.users_share_family", return_value=False), \
         patch(f"{ACCESS}.find_accepted_connection_between", return_value=object()) as m_conn:
        assert access.can_view_list(None, _user(2), _list(5, owner_id=1)) is False
        m_conn.assert_not_called()


# ---------------------------------------------------------------------------
# users_share_access  (accepted connection OR shared-family)
# ---------------------------------------------------------------------------


def test_users_share_access_connection_returns_true():
    with patch(f"{ACCESS}.find_accepted_connection_between", return_value=object()), \
         patch(f"{ACCESS}.users_share_family") as m_fam:
        assert access.users_share_access(None, 1, 2) is True
        m_fam.assert_not_called()  # short-circuits on the connection


def test_users_share_access_shared_family_returns_true():
    with patch(f"{ACCESS}.find_accepted_connection_between", return_value=None), \
         patch(f"{ACCESS}.users_share_family", return_value=True):
        assert access.users_share_access(None, 1, 2) is True


def test_users_share_access_neither_returns_false():
    with patch(f"{ACCESS}.find_accepted_connection_between", return_value=None), \
         patch(f"{ACCESS}.users_share_family", return_value=False):
        assert access.users_share_access(None, 1, 2) is False
