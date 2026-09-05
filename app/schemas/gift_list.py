from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, model_validator

from app.schemas.family import FamilyRef


class GiftListCreate(BaseModel):
    name: str
    description: str | None = None
    # Families to share the new list with. Ignored for simple-mode owners, who
    # share with every family they belong to (see app/list_families/service.py).
    family_ids: list[int] = []


class GiftListUpdate(BaseModel):
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
    is_archived: bool
    gifts: list[GiftRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
