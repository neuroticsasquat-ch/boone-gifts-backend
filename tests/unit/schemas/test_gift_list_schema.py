import pytest

from app.schemas.gift_list import (
    GiftListCreate,
    GiftListDetailOwner,
    GiftListDetailViewer,
    GiftListRead,
    GiftListUpdate,
)


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


# --- recipient_has_account is gone (NEU-1230) ---


@pytest.mark.parametrize(
    "schema",
    [GiftListCreate, GiftListUpdate, GiftListRead, GiftListDetailOwner,
     GiftListDetailViewer],
)
def test_recipient_has_account_is_not_a_field(schema):
    assert "recipient_has_account" not in schema.model_fields


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
def test_recipient_name_alone_is_accepted(schema):
    payload = schema(name="Christmas", recipient_name="Beth")
    assert payload.recipient_name == "Beth"


@pytest.mark.parametrize("schema", [GiftListCreate, GiftListUpdate])
def test_no_recipient_is_accepted(schema):
    payload = schema(name="Christmas")
    assert payload.recipient_name is None


def test_update_leaves_recipient_fields_unset_when_omitted():
    # exclude_unset is what lets a rename leave the recipient columns alone.
    updates = GiftListUpdate(name="Renamed").model_dump(exclude_unset=True)
    assert updates == {"name": "Renamed"}


def test_update_can_explicitly_clear_the_recipient():
    updates = GiftListUpdate(recipient_name=None).model_dump(exclude_unset=True)
    assert updates == {"recipient_name": None}
