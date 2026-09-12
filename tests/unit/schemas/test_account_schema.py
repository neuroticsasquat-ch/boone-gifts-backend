from app.schemas.account import AccountPersonWrite, AccountUpdate


def test_name_is_stripped():
    assert AccountPersonWrite(name="  Gran  ").name == "Gran"


def test_whitespace_only_name_survives_as_empty():
    # The schema only normalizes. Rejecting an empty name is the service's job,
    # so it can answer 400 rather than FastAPI's 422 (spec §4.3).
    assert AccountPersonWrite(name="   ").name == ""


def test_id_is_optional():
    assert AccountPersonWrite(name="Gran").id is None
    assert AccountPersonWrite(id=3, name="Gran").id == 3


def test_people_default_to_empty():
    assert AccountUpdate(is_shared_account=False).people == []
