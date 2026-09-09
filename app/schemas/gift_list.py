from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.schemas.claim import OccasionCandidate


class SharedViaFamily(BaseModel):
    """The family behind an occasion the list reached the viewer through. Derived
    from `occasions.family_id`, never stored on the share row (ADR 0002)."""

    id: int
    name: str


class SharedVia(BaseModel):
    """How a shared list reached the viewer: the owner who shared it directly, or
    the occasion it was shared to. Absent on a list the viewer owns.

    `family` rides along on the occasion arm only — the viewer needs to know
    which family an occasion belongs to, and it is one join away from a fact the
    query already has.
    """

    kind: Literal["user", "occasion"]
    id: int
    name: str
    family: SharedViaFamily | None = None

    @model_validator(mode="after")
    def _family_belongs_to_the_occasion_arm(self) -> "SharedVia":
        if self.kind == "occasion" and self.family is None:
            raise ValueError("An occasion share must carry its family.")
        if self.kind == "user" and self.family is not None:
            raise ValueError("A direct share has no family behind it.")
        return self


class RecipientFields(BaseModel):
    """The columns naming who a list is *for*, plus the invariants tying them
    together. Shared by the create and update payloads so the rules cannot
    drift between them."""

    recipient_name: str | None = None
    account_person_id: int | None = None

    @field_validator("recipient_name")
    @classmethod
    def normalize_recipient_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    # `account_person_id` and `recipient_name` are mutually exclusive — a list
    # is for an account person, or for someone with no account, or for neither
    # (spec §4.1, §4.2; supplying neither is a legal household list). That rule
    # is *not* here: a partial update cannot see the stored value of the other
    # field, and a ValueError in a request-body validator surfaces as 422 where
    # §4.1 asks for 400. app/lists/service.py enforces it against the resulting
    # row, which is the only place both halves are visible.


class GiftListCreate(RecipientFields):
    name: str
    description: str | None = None
    # Occasions to share the new list with, each on a family the owner belongs
    # to. Empty shares with nobody — there is no auto-grant (ADR 0002 §5.2 puts
    # the pre-checking in the client). See app/list_occasions/service.py.
    occasion_ids: list[int] = []


class GiftListUpdate(RecipientFields):
    name: str | None = None
    description: str | None = None
    is_archived: bool | None = None


class GiftOwnerRead(BaseModel):
    id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftRead(BaseModel):
    """A gift as somebody the list was **shared with** sees it: the gift, plus
    the claim standing on it.

    The claim lives on its own row now (ADR 0003), so the flat fields below are
    read through `Gift.claim` rather than off the gift. Flattening happens here
    and only here — `GiftOwnerRead` cannot pick it up by forgetting to exclude
    a column, because there is no column.
    """

    id: int
    name: str
    description: str | None
    url: str | None
    price: Decimal | None
    claimed_by_id: int | None = None
    claimed_at: datetime | None = None
    purchased_at: datetime | None = None
    amount_paid: Decimal | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def flatten_claim(cls, data: object) -> object:
        if not hasattr(data, "claim"):
            return data
        claim = data.claim
        # `occasion_id` is in this dict and deliberately not a field on
        # `GiftRead`, so Pydantic drops it here. The claimer's filing is private
        # to the claimer, and this schema is handed to every viewer of the list.
        # `GiftClaimRead` declares it, and is only ever returned to the claimer.
        return {
            "id": data.id,
            "name": data.name,
            "description": data.description,
            "url": data.url,
            "price": data.price,
            "claimed_by_id": claim.user_id if claim else None,
            "claimed_at": claim.claimed_at if claim else None,
            "purchased_at": claim.purchased_at if claim else None,
            "amount_paid": claim.amount_paid if claim else None,
            "occasion_id": claim.occasion_id if claim else None,
            "created_at": data.created_at,
            "updated_at": data.updated_at,
        }


class GiftClaimRead(GiftRead):
    """A gift as the **claimer** sees it the moment they claim it: the gift, the
    claim, and the occasion the claim was actually filed under.

    The filing is the one piece of claim state nobody but the claimer may see,
    so it lives on a schema returned only from endpoints where the caller is by
    definition the claimer. Every claim response states the filing recorded,
    because the server may have resolved, or silently corrected, what the client
    asked for (NEU-1269 §3.1).
    """

    occasion_id: int | None = None


class GiftListRead(BaseModel):
    """A list row as its **owner** sees it — and the base every other list-row
    response is built from, so claim state can only ever be added deliberately.

    It carries no claim state at all. `claimed_count` used to live here and was
    returned for every row `GET /lists` produced, owned ones included: the leak
    that motivated ADR 0003. It is on `GiftListViewerRead` now, which is only
    ever handed a list the caller does not own.
    """

    id: int
    name: str
    description: str | None
    owner_id: int
    owner_name: str
    recipient_name: str | None = None
    account_person_id: int | None = None
    account_person_name: str | None = None
    is_archived: bool
    gift_count: int = 0
    shared_via: SharedVia | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftListViewerRead(GiftListRead):
    """A list row as somebody the list was **shared with** sees it: how much of
    it is already spoken for, and how much of that is still theirs to buy. Hand
    it only a list the caller does not own — `app/lists/service.py:to_summary`
    is the one place that chooses."""

    claimed_count: int = 0
    # The `• N to buy` badge on the Lists dashboard (project spec §9.1). On a
    # directly shared list it is the *only* route back to the claim: that claim
    # files under no occasion and, unless its list sits in a folder, appears on
    # no shopping tab at all (§9.4). Unlike `claimed_count` it is a fact about
    # one caller, which is why validation needs to be told who is asking.
    #
    # Deliberately required rather than defaulted to 0: a default would let any
    # path that skips the validator below mint an empty badge that reads as
    # "nothing left to buy" instead of failing. Pydantic itself is then the
    # backstop, whatever shape the input arrives in.
    my_unpurchased_claim_count: int

    @model_validator(mode="before")
    @classmethod
    def count_claims(cls, data: object, info: ValidationInfo) -> object:
        if not hasattr(data, "gifts"):
            # No gifts to walk, so there is nothing to count here: either an
            # already-built row being revalidated (a folder's nested `lists`),
            # which carries both counts already, or a mapping that has to state
            # them itself. Neither needs a viewer, and a mapping that omits the
            # count is refused by the required field rather than defaulted.
            return data
        viewer_id = (info.context or {}).get("viewer_id")
        if viewer_id is None:
            raise ValueError(
                "GiftListViewerRead needs a viewer_id in its validation "
                "context: my_unpurchased_claim_count is a fact about one "
                "caller, and defaulting it would empty the badge silently "
                "rather than fail. Go through app/lists/service.py:to_summary."
            )
        # Read every declared field off the row as usual, then add the two
        # things the row cannot answer for itself.
        values = {
            name: getattr(data, name)
            for name in cls.model_fields
            if hasattr(data, name)
        }
        # Both counts come off the claims already loaded with the row rather
        # than a query per list: `GiftList.gifts` and `Gift.claim` are both
        # selectin, so a whole shared scope costs two queries, not two per row.
        claims = [g.claim for g in data.gifts if g.claim is not None]
        values["claimed_count"] = len(claims)
        values["my_unpurchased_claim_count"] = sum(
            1
            for claim in claims
            if claim.user_id == viewer_id and claim.purchased_at is None
        )
        return values


class GiftListDetailOwner(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    owner_name: str
    recipient_name: str | None = None
    account_person_id: int | None = None
    account_person_name: str | None = None
    is_archived: bool
    gifts: list[GiftOwnerRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GiftListDetailViewer(BaseModel):
    """A list's detail as somebody the list was **shared with** sees it.

    `claim_candidates` and `claim_options` ride here and **never** on
    `GiftListDetailOwner`: they are derived from the viewer's own memberships,
    so they would be meaningless on an owner's response — and this is precisely
    the class of field that produced the `claimed_count` leak (ADR 0003).
    """

    id: int
    name: str
    description: str | None
    owner_id: int
    owner_name: str
    recipient_name: str | None = None
    account_person_id: int | None = None
    account_person_name: str | None = None
    is_archived: bool
    gifts: list[GiftRead]
    # `suggested`: what the client renders, and counts to decide whether to
    # prompt at all. Two or more means prompt — claiming without asking is what
    # the 400 on the claim endpoint exists to catch.
    claim_candidates: list[OccasionCandidate] = []
    # `allowed`: the same set widened to include archived occasions, so the
    # picker can offer "show past occasions" without a second request. Without
    # it the correction path exists in the API and no UI can reach it (§2.2).
    claim_options: list[OccasionCandidate] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
