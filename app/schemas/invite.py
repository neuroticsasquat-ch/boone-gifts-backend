from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, computed_field


class InviteStatus(StrEnum):
    pending = "pending"
    used = "used"
    expired = "expired"


class InviteCreate(BaseModel):
    email: str
    role: str = "member"
    expires_in_days: int = 7


class InviteRead(BaseModel):
    id: int
    token: str
    email: str
    role: str
    expires_at: datetime
    used_at: datetime | None
    invited_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> InviteStatus:
        if self.used_at is not None:
            return InviteStatus.used
        # SQLite returns naive datetimes; compare without tzinfo to handle both cases.
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            now = now.replace(tzinfo=None)
        if expires < now:
            return InviteStatus.expired
        return InviteStatus.pending
