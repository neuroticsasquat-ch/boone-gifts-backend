from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class BudgetWrite(BaseModel):
    """The target the user is setting, on `PUT .../budget` — the overall's or
    one giftee's, the same shape for both.

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

    `amount` is the target the user *set*, or null: it remains the client's one
    predicate for offering *set* versus *edit*. `target` is what the money line
    is measured against — `amount` when set, else the sum of the caller's
    giftee budgets when at least one exists, else null — and `remaining` is
    `target − spent`, null when `target` is. Both may go negative: a budget is
    a target, not a limit, and hiding an overspend or an over-allocation would
    be the one thing a budget line must not do.

    `allocated` is the sum of the caller's giftee budgets in scope (`0.00` when
    none), `unallocated` is `amount − allocated` (null when `amount` is), and
    `allocation_count` is how many giftee budgets exist — what lets the client
    say "the sum of 3 people's budgets". A giftee's own rollup is a leaf:
    `allocated = 0.00`, `unallocated = None`, `target = amount`,
    `allocation_count = 0` — the same shape, so one line renders either.

    **The money total always discloses its own incompleteness.** A purchase
    with no amount recorded counts toward `bought_count` and toward
    `unpriced_count` and never toward `spent`, so a client that renders
    `unpriced_count` reads an understated total as an understatement rather
    than as fact.

    **`spent` counts ticked claims only.** An amount held on a claim that is
    not ticked bought is kept on the claim — re-ticking need not retype it —
    but counts as zero here until it is ticked again (NEU-1325).
    """

    amount: Decimal | None
    spent: Decimal
    remaining: Decimal | None
    bought_count: int
    total_count: int
    unpriced_count: int
    allocated: Decimal
    unallocated: Decimal | None
    target: Decimal | None
    allocation_count: int


class GifteeRead(BaseModel):
    """One giftee in a scope, as the shopping tab groups by (NEU-1326).

    `key` is the server-minted handle the client sends back on a write and
    never reads inside. `keeper` is the owner's name for a `person` or `absent`
    giftee — the account the list is kept on — and null for an `owner`.
    `list_count` is how many lists in scope resolve to this giftee; the client
    names a row's list only when it is more than one.

    Everything here is derived from lists the caller can already view, and the
    rollup counts the caller's own claims alone.
    """

    key: str
    kind: Literal["owner", "person", "absent"]
    name: str
    keeper: str | None
    list_count: int
    budget: BudgetRollup


class BudgetBlock(BaseModel):
    """The overall rollup and every giftee in scope with theirs.

    A giftee write answers with the block rather than one rollup because it
    moves two things at once: that giftee's line and the overall's `allocated`
    and `target`.
    """

    budget: BudgetRollup
    giftees: list[GifteeRead]
