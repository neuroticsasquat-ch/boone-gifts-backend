from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.gift_list import GiftListRead, GiftListViewerRead


class FolderCreate(BaseModel):
    """Schema for creating a new folder."""

    name: str
    description: str | None = None


class FolderUpdate(BaseModel):
    """Schema for updating an existing folder."""

    name: str | None = None
    description: str | None = None
    is_archived: bool | None = None


class FolderRead(BaseModel):
    """Schema for reading a folder without nested lists."""

    id: int
    name: str
    description: str | None
    owner_id: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FolderDetail(BaseModel):
    """Schema for reading a folder with its nested gift lists."""

    id: int
    name: str
    description: str | None
    owner_id: int
    is_archived: bool
    # Viewer schema first: it is the more specific arm, and a folder's rows are
    # a mix. Narrowing a viewer row to the owner schema would silently drop
    # `claimed_count`, which is what this field used to do.
    lists: list[GiftListViewerRead | GiftListRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FolderItemCreate(BaseModel):
    """Schema for adding a gift list to a folder."""

    list_id: int


class ShoppingListItem(BaseModel):
    """Schema for a single item in a folder's shopping list."""

    id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    list_id: int
    list_name: str
    purchased_at: datetime | None

    model_config = {"from_attributes": True}
