from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ListFamilyShare(Base):
    """A list owner's explicit opt-in to share one list with one family.

    A row implies the owner is still a member of that family: grants are deleted
    whenever the owner loses membership, so the read queries do not re-check it.
    """

    __tablename__ = "list_family_shares"
    __table_args__ = (
        UniqueConstraint("list_id", "family_id", name="uq_list_family_shares_list_family"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"), index=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
