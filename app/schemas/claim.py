from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PurchaseCreate(BaseModel):
    """What the claimer paid, when they tick a gift purchased.

    Optional, and optional in two distinct ways the service tells apart: an
    omitted `amount_paid` leaves whatever is already recorded alone, so
    unticking and re-ticking does not lose it, while an explicit null clears it.
    Skipping the amount is a first-class answer — a budget total that is honest
    about being incomplete beats one padded with the owner's asking price.
    """

    amount_paid: Decimal | None = None


class ClaimCreate(BaseModel):
    """Where the claimer wants this claim filed, when they claim a gift.

    The whole body is optional and so is the field, which the service tells
    apart from an explicit null: omitting it asks the server to resolve the
    filing from the suggestions, while `null` is the claimer deliberately
    filing under nothing (NEU-1269 §3.1).
    """

    occasion_id: int | None = None


class ClaimUpdate(BaseModel):
    """A correction to the claimer's own claim.

    Read with `model_dump(exclude_unset=True)`, so an omitted field is left
    alone — an amount-only edit must never disturb the filing, and vice versa.
    """

    occasion_id: int | None = None
    amount_paid: Decimal | None = None


class CandidateFamily(BaseModel):
    """The family behind a filing candidate. Two families routinely run
    occasions with the same name, so the picker cannot label one without it."""

    id: int
    name: str


class OccasionCandidate(BaseModel):
    """One occasion a claim on this list may be filed under, as the claimer's
    picker needs to render it.

    Carries `is_archived` because `claim_options` deliberately includes past
    occasions (§2.2) and the picker has to say so.
    """

    id: int
    name: str
    is_archived: bool
    family: CandidateFamily


class ClaimRead(BaseModel):
    """A claim as its own claimer sees it. Never handed to anyone else: the
    filing is private to the claimer, and the list's owner sees no claim state
    at all (ADR 0003)."""

    id: int
    gift_id: int
    occasion_id: int | None
    claimed_at: datetime
    purchased_at: datetime | None
    amount_paid: Decimal | None

    model_config = {"from_attributes": True}
