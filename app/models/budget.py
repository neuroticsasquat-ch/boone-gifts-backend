from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Budget(Base):
    """What one user means to spend on one occasion, or on one folder.

    **Always private to the user who set it** (`CONTEXT.md` invariant 1). There
    is no family budget and no aggregate anywhere: if Gran could watch the
    Boone Christmas total move, she would learn something had been claimed, and
    in a small family she could often work out what. `user_id` is therefore
    always the claimer, and every query here is keyed on it.

    `occasion_id` and `folder_id` are **mutually exclusive, and exactly one is
    set** — a budget hangs off one scope or the other, never both and never
    neither. That rule lives in `app/budgets/service.py` rather than in a check
    constraint: SQLite cannot add one without `render_as_batch` recreating the
    table, and the service is where the 400 has to be raised anyway.

    The two unique constraints are what make "one budget per scope" structural.
    They coexist because a NULL never collides in a unique index, so every
    occasion budget is free to leave `folder_id` null and vice versa.
    """

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "occasion_id", name="uq_budgets_user_occasion"),
        UniqueConstraint("user_id", "folder_id", name="uq_budgets_user_folder"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    occasion_id: Mapped[int | None] = mapped_column(
        ForeignKey("occasions.id"), default=None
    )
    folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("folders.id"), default=None
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
