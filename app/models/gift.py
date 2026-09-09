from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.claim import Claim


class Gift(Base):
    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    url: Mapped[str | None] = mapped_column(String(2048), default=None)
    # The *owner's* asking price, public to everyone who can see the list. What
    # a claimer actually spent is `claims.amount_paid`, and is private to them.
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # There is deliberately no claim state on this row (ADR 0003) — it is the
    # row the list's owner reads. The claim hangs off it instead, and only
    # viewer-facing schemas ever look through this relationship.
    claim: Mapped["Claim | None"] = relationship(
        "Claim", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )
