from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class SharedVia(BaseModel):
    """How a shared list reached the viewer: the owner who shared it directly, or
    the family it was granted to. Absent on a list the viewer owns."""

    kind: Literal["user", "family"]
    id: int
    name: str


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
    # Families to share the new list with. Ignored for simple-mode owners, who
    # share with every family they belong to (see app/list_families/service.py).
    family_ids: list[int] = []


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
    id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    claimed_by_id: int | None
    claimed_at: datetime | None
    purchased_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftListRead(BaseModel):
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
    claimed_count: int = 0
    shared_via: SharedVia | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def compute_counts(cls, data: object) -> object:
        if hasattr(data, "gifts"):
            gifts = data.gifts
            return {
                "id": data.id,
                "name": data.name,
                "description": data.description,
                "owner_id": data.owner_id,
                "owner_name": data.owner_name,
                "recipient_name": data.recipient_name,
                "account_person_id": data.account_person_id,
                "account_person_name": data.account_person_name,
                "is_archived": data.is_archived,
                "gift_count": len(gifts),
                "claimed_count": sum(1 for g in gifts if g.claimed_by_id is not None),
                "shared_via": getattr(data, "shared_via", None),
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data


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
