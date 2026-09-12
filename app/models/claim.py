from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Claim(Base):
    """One account's private intent to buy a gift, with what it cost.

    The claim used to be three columns on `gifts` — the row the list's *owner*
    reads — which made owner-blindness serializer discipline rather than
    structure, and had already leaked once (ADR 0003). It lives here now, so an
    owner-facing response has nothing claim-shaped to forget.

    `occasion_id` is not "which occasion this gift was claimed for": a claim is
    a single global fact about a gift. It is the claimer's own private filing of
    their spend, so it lands in exactly one budget, and is deliberately stored
    rather than derived from the share — a budget whose history rewrites itself
    when someone revokes a share or archives an occasion is worse than no
    budget. Filing is resolved when the claim is made (NEU-1269); every claim
    written here files under null.
    """

    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("gift_id", name="uq_claims_gift"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Unique, so one gift has at most one claimer — today's behaviour exactly.
    # Splitting the cost between two claimers would relax this constraint
    # rather than need a different shape.
    gift_id: Mapped[int] = mapped_column(ForeignKey("gifts.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    occasion_id: Mapped[int | None] = mapped_column(
        ForeignKey("occasions.id"), default=None, index=True
    )
    claimed_at: Mapped[datetime] = mapped_column()
    purchased_at: Mapped[datetime | None] = mapped_column(default=None)
    # What the *claimer* spent, as opposed to `gifts.price`, which is the
    # owner's asking price and is public to everyone who can see the list.
    amount_paid: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), default=None
    )
