from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FolderItem(Base):
    __tablename__ = "folder_items"
    __table_args__ = (
        UniqueConstraint(
            "folder_id", "list_id", name="uq_folder_items_folder_list"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id"))
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
