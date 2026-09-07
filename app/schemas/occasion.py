from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.gift_list import GiftListRead


class OccasionCreate(BaseModel):
    """Schema for creating a new occasion."""

    name: str
    description: str | None = None


class OccasionUpdate(BaseModel):
    """Schema for updating an existing occasion."""

    name: str | None = None
    description: str | None = None
    is_archived: bool | None = None


class OccasionRead(BaseModel):
    """Schema for reading an occasion without nested lists."""

    id: int
    name: str
    description: str | None
    owner_id: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OccasionDetail(BaseModel):
    """Schema for reading an occasion with its nested gift lists."""

    id: int
    name: str
    description: str | None
    owner_id: int
    is_archived: bool
    lists: list[GiftListRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OccasionItemCreate(BaseModel):
    """Schema for adding a gift list to an occasion."""

    list_id: int


class ShoppingListItem(BaseModel):
    """Schema for a single item in an occasion's shopping list."""

    id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    list_id: int
    list_name: str
    purchased_at: datetime | None

    model_config = {"from_attributes": True}
