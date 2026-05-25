from datetime import datetime

from pydantic import BaseModel

from app.schemas.gift_list import GiftListRead


class UserRead(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    lists: list[GiftListRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserSearchResult(BaseModel):
    id: int
    email: str
    name: str

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    email: str | None = None
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
