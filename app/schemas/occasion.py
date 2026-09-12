from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class OccasionCreate(BaseModel):
    """Schema for creating a family occasion."""

    name: str


class OccasionUpdate(BaseModel):
    """Schema for renaming or (un)archiving an occasion.

    The two fields carry **different gates**, applied in `app/occasions/service.py`
    rather than here: `name` is organizer-only, `is_archived` takes an organizer
    or the occasion's creator (`CONTEXT.md` invariant 9). A body setting both
    therefore needs the organizer role. This schema cannot express that — it
    validates shape, and the role belongs to the caller, not the payload.

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


class OccasionDetailRead(OccasionRead):
    """The detail read, naming the family that owns the occasion.

    A sibling of `OccasionSummary` rather than a field on `OccasionRead`,
    which answers four endpoints: putting `family_name` on the base would
    oblige `GET /families/{family_id}/occasions` to resolve a name its own
    route already carries. The two `family_name` declarations are duplicated
    deliberately — the index and the page are separate contracts with
    separate callers, and collapsing them into an inheritance chain to save a
    line would couple the strip's payload to the page's.

    The occasion page's heading reads "Boone Family · Christmas 2026", so the
    name has to arrive with the occasion itself: the page's family query does
    not fire until the occasion has resolved, and deriving the heading from it
    would paint the occasion name first and shove it sideways a round trip
    later (NEU-1321).
    """

    family_name: str


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


class ArchivePrompt(BaseModel):
    """One occasion the caller is being asked to archive, and nothing else.

    Purpose-built rather than derived from `OccasionRead` or `OccasionSummary`.
    The banner that consumes it names the occasion and its family and no more —
    no counts, no claimers, no gifts — and the narrowness is the guarantee:
    subclassing would put `my_claimed_count` and `my_bought_count` on a banner
    payload and drag `list_count` and both claim subqueries into a query that
    needs none of them. There is no field here that could ever carry claim
    state.

    `id`, not `occasion_id`: it matches every other occasion payload, and it is
    what the dismiss and archive calls take.

    **No `quiet_since`.** Now that the clock reads no claim at all a date would
    be safe to expose, but the banner does not want one — and a `datetime` on a
    prompt invites the next reader to assume it is `last_activity_at`, which it
    deliberately is not.
    """

    id: int
    name: str
    family_id: int
    family_name: str

    model_config = {"from_attributes": True}
