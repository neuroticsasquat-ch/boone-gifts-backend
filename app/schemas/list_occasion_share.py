from pydantic import BaseModel


class ShareTargetOccasion(BaseModel):
    """One occasion the list can be shared to, and whether it already is.

    `is_archived` is only ever true on an occasion the list is *already* shared
    to — archiving blocks new shares without withdrawing old ones, so the name
    still has to be displayable.
    """

    id: int
    name: str
    is_archived: bool
    shared: bool


class ShareTargetFamily(BaseModel):
    """One family the list's owner belongs to, with its shareable occasions.

    An empty `occasions` is the "no active occasion" state: the family is still
    listed, because the control renders it disabled with the reason given rather
    than hiding it (ADR 0002 §5.2).
    """

    id: int
    name: str
    occasions: list[ShareTargetOccasion]
