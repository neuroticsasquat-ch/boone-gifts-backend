from datetime import datetime

from pydantic import BaseModel


class ListShareCreate(BaseModel):
    user_id: int


class ListShareRead(BaseModel):
    id: int
    list_id: int
    user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SharedUserRead(BaseModel):
    id: int
    name: str
    email: str

    model_config = {"from_attributes": True}
