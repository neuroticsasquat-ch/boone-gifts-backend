from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.budget import BudgetRollup


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


class ShoppingItem(BaseModel):
    """One line on a shopping tab: the caller's own claim, and the gift it
    stands on.

    Only ever the caller's own — there is no parameter, no admin path and no
    aggregate that returns anyone else's (`CONTEXT.md` invariant 1). `price` is
    the *owner's* asking price, public to every viewer of the list;
    `amount_paid` is what the claimer actually spent and is private to them.
    Never seed one from the other.

    `claim_id` is here because correcting the filing or the amount goes through
    `PATCH /claims/{id}`, which the tab has no other way to address (§6.2).
    """

    claim_id: int
    gift_id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    list_id: int
    list_name: str
    purchased_at: datetime | None
    amount_paid: Decimal | None


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


class ShoppingPayload(BaseModel):
    """A shopping tab: the caller's own claims, and the budget they count
    against.

    The rollup travels with the items rather than behind a second endpoint
    because the two are one screen and must agree — a budget line fetched
    separately can render a total that the list beside it contradicts.
    """

    budget: BudgetRollup
    items: list[ShoppingItem]
