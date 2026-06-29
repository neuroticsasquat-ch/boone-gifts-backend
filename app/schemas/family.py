from typing import Literal

from pydantic import BaseModel


class FamilyRef(BaseModel):
    """Minimal family reference used to annotate family-visible lists."""

    id: int
    name: str

    model_config = {"from_attributes": True}


class FamilyCreate(BaseModel):
    name: str


class FamilyUpdate(BaseModel):
    name: str


class FamilyMemberInfo(BaseModel):
    user_id: int
    name: str
    role: str


class FamilyRead(BaseModel):
    id: int
    name: str
    role: str
    member_count: int

    model_config = {"from_attributes": True}


class FamilyDetail(BaseModel):
    id: int
    name: str
    created_by_id: int
    members: list[FamilyMemberInfo]

    model_config = {"from_attributes": True}


class FamilyMemberRoleUpdate(BaseModel):
    role: Literal["organizer", "member"]
