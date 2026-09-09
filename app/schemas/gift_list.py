from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class SharedViaFamily(BaseModel):
    """The family behind an occasion the list reached the viewer through. Derived
    from `occasions.family_id`, never stored on the share row (ADR 0002)."""

    id: int
    name: str


class SharedVia(BaseModel):
    """How a shared list reached the viewer: the owner who shared it directly, or
    the occasion it was shared to. Absent on a list the viewer owns.

    `family` rides along on the occasion arm only — the viewer needs to know
    which family an occasion belongs to, and it is one join away from a fact the
    query already has.
    """

    kind: Literal["user", "occasion"]
    id: int
    name: str
    family: SharedViaFamily | None = None

    @model_validator(mode="after")
    def _family_belongs_to_the_occasion_arm(self) -> "SharedVia":
        if self.kind == "occasion" and self.family is None:
            raise ValueError("An occasion share must carry its family.")
        if self.kind == "user" and self.family is not None:
            raise ValueError("A direct share has no family behind it.")
        return self


class RecipientFields(BaseModel):
    """The columns naming who a list is *for*, plus the invariants tying them
    together. Shared by the create and update payloads so the rules cannot
    drift between them."""

    recipient_name: str | None = None
    account_person_id: int | None = None

    @field_validator("recipient_name")
    @classmethod
    def normalize_recipient_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    # `account_person_id` and `recipient_name` are mutually exclusive — a list
    # is for an account person, or for someone with no account, or for neither
    # (spec §4.1, §4.2; supplying neither is a legal household list). That rule
    # is *not* here: a partial update cannot see the stored value of the other
    # field, and a ValueError in a request-body validator surfaces as 422 where
    # §4.1 asks for 400. app/lists/service.py enforces it against the resulting
    # row, which is the only place both halves are visible.


class GiftListCreate(RecipientFields):
    name: str
    description: str | None = None
    # Occasions to share the new list with, each on a family the owner belongs
    # to. Empty shares with nobody — there is no auto-grant (ADR 0002 §5.2 puts
    # the pre-checking in the client). See app/list_occasions/service.py.
    occasion_ids: list[int] = []


class GiftListUpdate(RecipientFields):
    name: str | None = None
    description: str | None = None
    is_archived: bool | None = None


class GiftOwnerRead(BaseModel):
    id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftRead(BaseModel):
    """A gift as somebody the list was **shared with** sees it: the gift, plus
    the claim standing on it.

    The claim lives on its own row now (ADR 0003), so the flat fields below are
    read through `Gift.claim` rather than off the gift. Flattening happens here
    and only here — `GiftOwnerRead` cannot pick it up by forgetting to exclude
    a column, because there is no column.
    """

    id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    claimed_by_id: int | None = None
    claimed_at: datetime | None = None
    purchased_at: datetime | None = None
    amount_paid: Decimal | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def flatten_claim(cls, data: object) -> object:
        if not hasattr(data, "claim"):
            return data
        claim = data.claim
        return {
            "id": data.id,
            "name": data.name,
            "description": data.description,
            "url": data.url,
            "price": data.price,
            "claimed_by_id": claim.user_id if claim else None,
            "claimed_at": claim.claimed_at if claim else None,
            "purchased_at": claim.purchased_at if claim else None,
            "amount_paid": claim.amount_paid if claim else None,
            "created_at": data.created_at,
            "updated_at": data.updated_at,
        }


class GiftListRead(BaseModel):
    """A list row as its **owner** sees it — and the base every other list-row
    response is built from, so claim state can only ever be added deliberately.

    It carries no claim state at all. `claimed_count` used to live here and was
    returned for every row `GET /lists` produced, owned ones included: the leak
    that motivated ADR 0003. It is on `GiftListViewerRead` now, which is only
    ever handed a list the caller does not own.
    """

    id: int
    name: str
    description: str | None
    owner_id: int
    owner_name: str
    recipient_name: str | None = None
    account_person_id: int | None = None
    account_person_name: str | None = None
    is_archived: bool
    gift_count: int = 0
    shared_via: SharedVia | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftListViewerRead(GiftListRead):
    """A list row as somebody the list was **shared with** sees it: how much of
    it is already spoken for. Hand it only a list the caller does not own —
    `app/lists/service.py:to_summary` is the one place that chooses."""

    claimed_count: int = 0

    @model_validator(mode="before")
    @classmethod
    def count_claims(cls, data: object) -> object:
        if not hasattr(data, "gifts"):
            return data
        # Read every declared field off the row as usual, then add the one
        # thing the row cannot answer for itself.
        values = {
            name: getattr(data, name)
            for name in cls.model_fields
            if hasattr(data, name)
        }
        values["claimed_count"] = sum(1 for g in data.gifts if g.claim is not None)
        return values


class GiftListDetailOwner(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    owner_name: str
    recipient_name: str | None = None
    account_person_id: int | None = None
    account_person_name: str | None = None
    is_archived: bool
    gifts: list[GiftOwnerRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftListDetailViewer(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    owner_name: str
    recipient_name: str | None = None
    account_person_id: int | None = None
    account_person_name: str | None = None
    is_archived: bool
    gifts: list[GiftRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
