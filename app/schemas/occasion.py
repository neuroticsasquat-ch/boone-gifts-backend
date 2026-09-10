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


class OccasionSummary(OccasionRead):
    """One row of the occasion index — the occasion plus what a card needs.

    Every added field is about the caller and nobody else. `my_claimed_count`
    and `my_bought_count` count the caller's own claims, and `last_activity_at`
    is the per-viewer clock of ADR 0005: the later of the last share into the
    occasion and the caller's *own* claim or purchase filed under it, floored at
    the occasion's creation so it is never null.

    It deliberately does **not** carry another user's claim, because the strip
    sorts on it — an occasion holding only the caller's own list rising to the
    top the moment somebody claimed from it is a badge by another name, and
    `CONTEXT.md` invariant 1 forbids it.
    """

    family_name: str
    list_count: int
    my_claimed_count: int
    my_bought_count: int
    last_activity_at: datetime
