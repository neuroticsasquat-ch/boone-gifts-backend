from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, computed_field, field_validator


class FamilyInviteStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"


class FamilyInviteCreate(BaseModel):
    email: str
    role: str = "member"
    simple_mode: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("member", "organizer"):
            raise ValueError("role must be 'member' or 'organizer'.")
        return v


class FamilyInviteRead(BaseModel):
    id: int
    family_id: int
    email: str
    role: str
    simple_mode: bool
    token: str
    invited_by_id: int
    expires_at: datetime
    accepted_at: datetime | None
    declined_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> FamilyInviteStatus:
        if self.accepted_at is not None:
            return FamilyInviteStatus.accepted
        if self.declined_at is not None:
            return FamilyInviteStatus.declined
        # SQLite returns naive datetimes; compare without tzinfo to handle both cases.
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            now = now.replace(tzinfo=None)
        if expires < now:
            return FamilyInviteStatus.expired
        return FamilyInviteStatus.pending


class FamilyRef(BaseModel):
    id: int
    name: str


class InviterRef(BaseModel):
    id: int
    name: str


class IncomingFamilyInviteRead(BaseModel):
    id: int
    token: str
    role: str
    family: FamilyRef
    invited_by: InviterRef
    expires_at: datetime
    created_at: datetime
