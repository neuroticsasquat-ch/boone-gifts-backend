from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ListShare(Base):
    __tablename__ = "list_shares"
    __table_args__ = (
        UniqueConstraint("list_id", "user_id", name="uq_list_shares_list_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    seen_at: Mapped[datetime | None] = mapped_column(default=None)
