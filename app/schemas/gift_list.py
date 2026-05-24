from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class GiftListCreate(BaseModel):
    name: str
    description: str | None = None


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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
