from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.account_person import AccountPerson
    from app.models.user import User
    from app.models.gift import Gift


class GiftList(Base):
    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recipient_name: Mapped[str | None] = mapped_column(String(255), default=None)
    account_person_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_people.id"), default=None, index=True
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship("User", lazy="selectin", overlaps="lists")

    account_person: Mapped["AccountPerson | None"] = relationship(
        "AccountPerson", lazy="selectin"
    )

    gifts: Mapped[list["Gift"]] = relationship(
        "Gift", lazy="selectin", cascade="all, delete-orphan"
    )

    @property
    def owner_name(self) -> str:
        return self.owner.name

    @property
    def account_person_name(self) -> str | None:
        """The label this list carries, or None. A label, not an identity —
        it names one member of the owning account, never a separate user."""
        return self.account_person.name if self.account_person else None

    @property
    def kept_for_absent_person(self) -> bool:
        """This list is kept on behalf of someone who has no account and will never
        log in. That is now the only thing a recipient can mean — a co-resident who
        reads this list on the same login is an account person instead.

        Read this rather than testing `recipient_name` directly: callers care about
        the question, not the column that happens to answer it."""
        return self.recipient_name is not None
