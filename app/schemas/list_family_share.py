from pydantic import BaseModel


class ListFamilyShareState(BaseModel):
    """One family the list owner belongs to, and whether the list is shared with it."""

    id: int
    name: str
    shared: bool
