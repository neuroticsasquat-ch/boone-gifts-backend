from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OccasionItem(Base):
    __tablename__ = "occasion_items"
    __table_args__ = (
        UniqueConstraint(
            "occasion_id", "list_id", name="uq_occasion_items_occasion_list"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    occasion_id: Mapped[int] = mapped_column(ForeignKey("occasions.id"))
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
