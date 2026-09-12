from pydantic import BaseModel, field_validator


class AccountPersonRead(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class AccountPersonWrite(BaseModel):
    """One entry of the desired people list. An `id` the caller owns renames
    that person in place; no `id` creates one. Array order is display order."""

    id: int | None = None
    name: str

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        # Strip only, following family_invite.py's normalizer. Rejecting what is
        # left of nothing happens in the service: a ValueError raised here would
        # surface as FastAPI's 422, and §4.3 asks for a 400.
        return v.strip()


class AccountRead(BaseModel):
    is_shared_account: bool
    people: list[AccountPersonRead]


class AccountUpdate(BaseModel):
    """The whole desired state of the account's people — a declarative full
    replace, which is what a settings card's Save button submits. Anyone
    omitted from `people` is deleted."""

    is_shared_account: bool
    people: list[AccountPersonWrite] = []


class AccountConflict(BaseModel):
    """The 409 body. A bare count: unlike the family-revoke 409 it discloses
    nothing sensitive, but it stays a count for symmetry with that idiom."""

    affected_lists: int
