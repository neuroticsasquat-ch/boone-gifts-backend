from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GifteeBudget(Base):
    """What one user means to spend on one giftee within one occasion or folder.

    As private as a `Budget` (`CONTEXT.md` invariant 1): `user_id` is always the
    caller, and every query is keyed on it. The overall budget and the giftee
    budgets are independent rows — allocating to giftees never writes the
    overall, and neither path reads the other's table (NEU-1326 decision 5).

    A giftee is derived from a list's three columns, never stored as its own row
    (ADR 0006), so this row carries **both** the triple and the canonical key
    built from it. Uniqueness needs a single non-null column: SQLite never
    collides two NULLs in a unique index, so `(owner_id, NULL, NULL)` would be
    storable twice. The cascades need real foreign keys, because "or the FK
    refuses" is how this repo catches a forgotten teardown (invariant 10). The
    service is the only writer of all four and derives the key from the triple,
    so they cannot disagree.

    `occasion_id` and `folder_id` are mutually exclusive with exactly one set,
    enforced by `app/budgets/service.py:_require_one_scope` for the same reason
    the `budgets` table has no check constraint.
    """

    __tablename__ = "giftee_budgets"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "occasion_id",
            "giftee_key",
            name="uq_giftee_budgets_user_occasion_key",
        ),
        UniqueConstraint(
            "user_id",
            "folder_id",
            "giftee_key",
            name="uq_giftee_budgets_user_folder_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    occasion_id: Mapped[int | None] = mapped_column(
        ForeignKey("occasions.id"), default=None
    )
    folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("folders.id"), default=None
    )
    # The opaque handle the API addresses a giftee by (decision 1).
    giftee_key: Mapped[str] = mapped_column(String(300))
    # The list owner the giftee resolves through — the giftee themself for an
    # `owner` key, the keeper for `person` and `absent`.
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    account_person_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_people.id"), default=None, index=True
    )
    recipient_name: Mapped[str | None] = mapped_column(String(255), default=None)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
