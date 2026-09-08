from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccountPerson(Base):
    """A named person on a shared account — a *label*, never an identity.

    The account remains the single identity everywhere: one family member, one
    connection, one claimer. Nothing about visibility, claims, membership or
    attribution knows these rows exist. See
    `docs/adr/0001-shared-accounts-are-one-identity.md`."""

    __tablename__ = "account_people"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_account_people_user_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    # Display order, 0-based. Persisted rather than derived so a reorder that
    # renames nothing still survives.
    position: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
