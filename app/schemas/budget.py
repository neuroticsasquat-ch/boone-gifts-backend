from decimal import Decimal

from pydantic import BaseModel, Field


class BudgetWrite(BaseModel):
    """The target the user is setting, on `PUT .../budget`.

    A budget is a whole target, not a delta, so the write is a plain replace —
    there is no create/update distinction to make the client care about. A
    negative target is meaningless rather than merely unusual, so it is refused
    by the schema; zero is allowed, and reads as "I mean to spend nothing here".
    """

    amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class BudgetRollup(BaseModel):
    """A budget and what the caller has spent against it.

    Returned on every write and beside every shopping payload, and **only ever
    about the caller's own claims** — no endpoint anywhere aggregates spend
    across accounts (`CONTEXT.md` invariant 1).

    `amount` and `remaining` are null when no budget is set: the counts are
    worth rendering regardless ("3 of 7 bought"), and null is what tells the
    client to offer *set* rather than *edit*. `remaining` may go negative — a
    budget is a target, not a limit, and hiding an overspend would be the one
    thing a budget line must not do.

    **The money total always discloses its own incompleteness.** A purchase
    with no amount recorded counts toward `bought_count` and toward
    `unpriced_count` and never toward `spent`, so a client that renders
    `unpriced_count` reads an understated total as an understatement rather
    than as fact.
    """

    amount: Decimal | None
    spent: Decimal
    remaining: Decimal | None
    bought_count: int
    total_count: int
    unpriced_count: int
