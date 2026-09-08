from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class OccasionCreate(BaseModel):
    """Schema for creating a family occasion."""

    name: str


class OccasionUpdate(BaseModel):
    """Schema for renaming or (un)archiving an occasion. Organizer-only.

    Both fields are optional to *supply*, never nullable: `None` is the "leave
    it alone" sentinel the router reads through `exclude_unset`, and neither
    column is nullable. An explicit `null` in the body is therefore a 422, not a
    write — validators do not run on defaults, so only a supplied one is caught.
    """

    name: str | None = None
    is_archived: bool | None = None

    @field_validator("name", "is_archived")
    @classmethod
    def _reject_explicit_null(cls, value: Any, info) -> Any:
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null.")
        return value


class OccasionRead(BaseModel):
    """Schema for reading a family occasion."""

    id: int
    family_id: int
    name: str
    is_archived: bool
    created_by_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OccasionCreateRead(OccasionRead):
    """The create response, carrying the warning signal the client needs.

    A second active occasion is allowed (ADR 0002 §5.3): the warning is a client
    concern, so `has_other_active` says whether the family already had an active
    occasion when this one was created — saving the client a second call.
    """

    has_other_active: bool
