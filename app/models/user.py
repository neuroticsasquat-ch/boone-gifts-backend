from datetime import datetime, timezone
from typing import TYPE_CHECKING

import bcrypt
from sqlalchemy import String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.gift_list import GiftList

# bcrypt's work factor. Each extra round doubles the time a hash costs, which is
# the point in production and pure overhead in a test suite that hashes a few
# hundred throwaway passwords: at 12 it is ~250ms a hash, and the suite spent
# more time here than on everything else combined. Named rather than left to
# `bcrypt.gensalt()`'s default so `tests/conftest.py` has one honest seam to
# lower it through, and so production cannot be lowered by an env var at all.
BCRYPT_ROUNDS = 12


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_shared_account: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=True
    )

    lists: Mapped[list["GiftList"]] = relationship(
        "GiftList", lazy="selectin", foreign_keys="GiftList.owner_id"
    )

    def set_password(self, password: str) -> None:
        salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
        self.password_hash = bcrypt.hashpw(password.encode(), salt).decode()

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode(), self.password_hash.encode())
