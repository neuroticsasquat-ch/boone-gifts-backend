import pytest
from pydantic import ValidationError

from app.schemas.gift_list import GiftListCreate, GiftListUpdate


# --- recipient_name normalization ---


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
def test_recipient_name_whitespace_only_normalizes_to_none(schema):
    payload = schema(name="Christmas", recipient_name="   ")
    assert payload.recipient_name is None


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
def test_recipient_name_is_stripped(schema):
    payload = schema(name="Christmas", recipient_name="  Beth  ")
    assert payload.recipient_name == "Beth"


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
def test_recipient_name_none_stays_none(schema):
    payload = schema(name="Christmas", recipient_name=None)
    assert payload.recipient_name is None


# --- the flag requires a name ---


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
@pytest.mark.parametrize("has_account", [True, False])
def test_flag_without_name_is_rejected(schema, has_account):
    with pytest.raises(ValidationError, match="requires a recipient_name"):
        schema(name="Christmas", recipient_has_account=has_account)


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
def test_flag_with_whitespace_only_name_is_rejected(schema):
    # The normalizer runs first, so "   " is None by the time the invariant is checked.
    with pytest.raises(ValidationError, match="requires a recipient_name"):
        schema(name="Christmas", recipient_name="  ", recipient_has_account=False)


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
@pytest.mark.parametrize("has_account", [True, False])
def test_name_with_flag_is_accepted(schema, has_account):
    payload = schema(
        name="Christmas", recipient_name="Beth", recipient_has_account=has_account
    )
    assert payload.recipient_name == "Beth"
    assert payload.recipient_has_account is has_account


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
def test_name_without_flag_is_accepted(schema):
    payload = schema(name="Christmas", recipient_name="Beth")
    assert payload.recipient_name == "Beth"
    assert payload.recipient_has_account is None


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
def test_neither_field_is_accepted(schema):
    payload = schema(name="Christmas")
    assert payload.recipient_name is None
    assert payload.recipient_has_account is None


def test_update_leaves_recipient_fields_unset_when_omitted():
    # exclude_unset is what lets a rename leave both columns alone.
    updates = GiftListUpdate(name="Renamed").model_dump(exclude_unset=True)
    assert updates == {"name": "Renamed"}


def test_update_can_explicitly_clear_both_fields():
    updates = GiftListUpdate(
        recipient_name=None, recipient_has_account=None
    ).model_dump(exclude_unset=True)
    assert updates == {"recipient_name": None, "recipient_has_account": None}
