from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.gift_list import (
    GiftListCreate,
    GiftListDetailOwner,
    GiftListDetailViewer,
    GiftListRead,
    GiftListUpdate,
    GiftListViewerRead,
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


# --- my_unpurchased_claim_count (NEU-1279) ---


def _row(gifts):
    """A minimal stand-in for the ORM row the viewer schema is validated from."""
    return SimpleNamespace(
        id=1,
        name="Jane's Wishlist",
        description=None,
        owner_id=99,
        owner_name="Jane",
        recipient_name=None,
        account_person_id=None,
        account_person_name=None,
        is_archived=False,
        gift_count=len(gifts),
        shared_via=[],
        gifts=gifts,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _gift(user_id=None, purchased=False):
    claim = (
        None
        if user_id is None
        else SimpleNamespace(
            user_id=user_id,
            purchased_at=datetime(2026, 1, 2) if purchased else None,
        )
    )
    return SimpleNamespace(claim=claim)


@pytest.mark.parametrize(
    "schema", [GiftListRead, GiftListDetailOwner, GiftListDetailViewer]
)
def test_only_the_viewer_row_carries_the_unpurchased_count(schema):
    """It is a fact about one caller's own claims, so it belongs on exactly the
    schema handed a list that caller does not own."""
    assert "my_unpurchased_claim_count" not in schema.model_fields
    assert "my_unpurchased_claim_count" in GiftListViewerRead.model_fields


def test_it_counts_only_the_viewers_own_unbought_claims():
    row = _row(
        [
            _gift(user_id=7),                    # mine, still to buy
            _gift(user_id=7, purchased=True),    # mine, already bought
            _gift(user_id=8),                    # someone else's
            _gift(),                             # unclaimed
        ]
    )
    read = GiftListViewerRead.model_validate(row, context={"viewer_id": 7})
    assert read.my_unpurchased_claim_count == 1
    assert read.claimed_count == 3


def test_a_viewer_with_no_claims_of_their_own_counts_zero():
    row = _row([_gift(user_id=8), _gift()])
    read = GiftListViewerRead.model_validate(row, context={"viewer_id": 7})
    assert read.my_unpurchased_claim_count == 0
    assert read.claimed_count == 1


def test_validating_without_a_viewer_is_refused():
    """A missing context would quietly count zero and empty the badge for
    everyone, which is exactly the silent failure `claimed_count` had."""
    with pytest.raises(ValidationError, match="viewer_id"):
        GiftListViewerRead.model_validate(_row([_gift(user_id=7)]))


def test_revalidating_a_built_row_needs_no_viewer():
    """A folder's `lists` are already-built viewer rows revalidated as part of
    `FolderDetail`; the counts ride along rather than being recomputed."""
    built = GiftListViewerRead.model_validate(
        _row([_gift(user_id=7)]), context={"viewer_id": 7}
    )
    again = GiftListViewerRead.model_validate(built)
    assert again.my_unpurchased_claim_count == 1
    assert again.claimed_count == 1


def test_a_mapping_that_omits_the_count_is_refused():
    """The other way in. A row built from a mapping never reaches the validator's
    counting branch — there are no gifts to walk — so nothing would compute the
    count, and a default would hand back an empty badge that reads as "nothing
    left to buy". The field is required so Pydantic refuses instead."""
    stated = {
        "id": 1,
        "name": "Jane's Wishlist",
        "description": None,
        "owner_id": 99,
        "owner_name": "Jane",
        "is_archived": False,
        "gift_count": 1,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }
    with pytest.raises(ValidationError, match="my_unpurchased_claim_count"):
        GiftListViewerRead.model_validate(stated)

    # Stating it is fine: the caller has taken responsibility for the number.
    read = GiftListViewerRead.model_validate(stated | {"my_unpurchased_claim_count": 2})
    assert read.my_unpurchased_claim_count == 2
