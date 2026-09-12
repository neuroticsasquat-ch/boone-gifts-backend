from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.account import service
from app.schemas.account import AccountPersonWrite, AccountUpdate
from app.services.exceptions import BadRequestError, NotFoundError

REPO = "app.account.service.repo"


def _person(id: int, name: str, position: int = 0) -> SimpleNamespace:
    return SimpleNamespace(id=id, name=name, position=position)


def _user(id: int = 1, is_shared_account: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=id, is_shared_account=is_shared_account)


def _desired(is_shared_account: bool, *people) -> AccountUpdate:
    return AccountUpdate(
        is_shared_account=is_shared_account,
        people=[AccountPersonWrite(id=id, name=name) for id, name in people],
    )


# --- shape rules (§4.3) ---


def test_empty_name_is_rejected():
    # The schema strips; what is left of nothing is a 400, not a 422.
    with pytest.raises(BadRequestError, match="needs a name"):
        service.replace_account(
            MagicMock(), _user(), _desired(True, (None, "   "), (None, "Grandpa"))
        )


def test_duplicate_names_are_rejected():
    with pytest.raises(BadRequestError, match="cannot share a name"):
        service.replace_account(
            MagicMock(), _user(), _desired(True, (None, "Gran"), (None, "Gran"))
        )


def test_repeated_id_is_rejected():
    with pytest.raises(BadRequestError, match="cannot appear twice"):
        service.replace_account(
            MagicMock(), _user(), _desired(True, (7, "Gran"), (7, "Grandpa"))
        )


@patch(f"{REPO}.get_people", return_value=[])
def test_marking_shared_with_fewer_than_two_people_is_rejected(mock_people):
    with pytest.raises(BadRequestError, match="at least two people"):
        service.replace_account(MagicMock(), _user(), _desired(True, (None, "Gran")))


@patch(f"{REPO}.get_people", return_value=[])
def test_marking_shared_with_no_people_is_rejected(mock_people):
    with pytest.raises(BadRequestError, match="at least two people"):
        service.replace_account(MagicMock(), _user(), _desired(True))


# --- ownership (§3.2) ---


@patch(f"{REPO}.get_people", return_value=[_person(1, "Gran")])
def test_unknown_person_id_is_not_found(mock_people):
    # Another account's id and an id that never existed are indistinguishable:
    # a 403 would confirm it exists.
    with pytest.raises(NotFoundError):
        service.replace_account(
            MagicMock(), _user(), _desired(True, (99, "Gran"), (None, "Grandpa"))
        )


@patch(f"{REPO}.get_person", return_value=None)
def test_get_owned_person_id_rejects_another_accounts_person(mock_get):
    db = MagicMock()
    with pytest.raises(NotFoundError):
        service.get_owned_person_id(db, owner_id=1, person_id=42)
    mock_get.assert_called_once_with(db, 1, 42)


def test_get_owned_person_id_passes_none_through():
    # A list with no label never touches the repository.
    assert service.get_owned_person_id(MagicMock(), owner_id=1, person_id=None) is None


# --- the destructive-change 409 (§3.3) ---


@patch(f"{REPO}.count_lists_for_people", return_value=2)
@patch(f"{REPO}.get_people")
def test_deleting_a_labelled_person_needs_confirmation(mock_people, mock_count):
    mock_people.return_value = [_person(1, "Gran", 0), _person(2, "Grandpa", 1)]
    db = MagicMock()

    with pytest.raises(service.LabelsWouldBeStripped) as excinfo:
        service.replace_account(
            db, _user(is_shared_account=True),
            _desired(True, (1, "Gran"), (None, "Dot")),
        )

    assert excinfo.value.affected_lists == 2
    mock_count.assert_called_once_with(db, 1, [2])
    db.flush.assert_not_called()


@patch(f"{REPO}.count_lists_labelled", return_value=3)
@patch(f"{REPO}.get_people")
def test_unmarking_shared_needs_confirmation(mock_people, mock_count):
    mock_people.return_value = [_person(1, "Gran", 0), _person(2, "Grandpa", 1)]

    with pytest.raises(service.LabelsWouldBeStripped) as excinfo:
        service.replace_account(
            MagicMock(), _user(is_shared_account=True),
            _desired(False, (1, "Gran"), (2, "Grandpa")),
        )

    # Unmarking strips *every* label, not just one person's.
    assert excinfo.value.affected_lists == 3


@patch(f"{REPO}.count_lists_for_people", return_value=0)
@patch(f"{REPO}.get_people")
def test_deleting_an_unlabelled_person_needs_no_confirmation(mock_people, mock_count):
    mock_people.return_value = [
        _person(1, "Gran", 0), _person(2, "Grandpa", 1), _person(3, "Dot", 2)
    ]
    user = _user(is_shared_account=True)

    service.replace_account(MagicMock(), user, _desired(True, (1, "Gran"), (2, "Grandpa")))

    assert user.is_shared_account is True
