from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator, model_validator

from app.schemas.family import FamilyRef


class RecipientFields(BaseModel):
    """The two columns naming who a list is *for*, plus the invariant tying them
    together. Shared by the create and update payloads so the rule cannot drift
    between them."""

    recipient_name: str | None = None
    recipient_has_account: bool | None = None

    @field_validator("recipient_name")
    @classmethod
    def normalize_recipient_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    @model_validator(mode="after")
    def require_name_with_account_answer(self):
        # A flag with no name is meaningless, and the two fields are one control
        # in the UI, so they always travel together.
        if self.recipient_has_account is not None and self.recipient_name is None:
            raise ValueError("recipient_has_account requires a recipient_name")
        return self


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
    recipient_has_account: bool | None = None
    is_archived: bool
    gift_count: int = 0
    claimed_count: int = 0
    families: list[FamilyRef] = []
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
                "recipient_has_account": data.recipient_has_account,
                "is_archived": data.is_archived,
                "gift_count": len(gifts),
                "claimed_count": sum(1 for g in gifts if g.claimed_by_id is not None),
                "families": getattr(data, "families", []),
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
    recipient_has_account: bool | None = None
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
    recipient_has_account: bool | None = None
    is_archived: bool
    gifts: list[GiftRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
