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
