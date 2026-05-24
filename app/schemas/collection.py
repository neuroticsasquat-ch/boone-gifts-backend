from datetime import datetime

from pydantic import BaseModel

from app.schemas.gift_list import GiftListRead


class CollectionCreate(BaseModel):
    """Schema for creating a new collection."""

    name: str
    description: str | None = None


class CollectionUpdate(BaseModel):
    """Schema for updating an existing collection."""

    name: str | None = None
    description: str | None = None
    is_archived: bool | None = None


class CollectionRead(BaseModel):
    """Schema for reading a collection without nested lists."""

    id: int
    name: str
    description: str | None
    owner_id: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionDetail(BaseModel):
    """Schema for reading a collection with its nested gift lists."""

    id: int
    name: str
    description: str | None
    owner_id: int
    is_archived: bool
    lists: list[GiftListRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionItemCreate(BaseModel):
    """Schema for adding a gift list to a collection."""

    list_id: int
