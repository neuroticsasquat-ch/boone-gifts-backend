from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ListOccasionShare(Base):
    """A list owner's explicit opt-in to share one list with one family occasion.

    The family is derived through `occasions.family_id` and is deliberately not
    stored twice (ADR 0002). A row implies the owner is still a member of that
    family: shares are deleted whenever the owner loses membership, so the read
    queries do not re-check it.
    """

    __tablename__ = "list_occasion_shares"
    __table_args__ = (
        UniqueConstraint(
            "list_id", "occasion_id", name="uq_list_occasion_shares_list_occasion"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"), index=True)
    occasion_id: Mapped[int] = mapped_column(ForeignKey("occasions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
