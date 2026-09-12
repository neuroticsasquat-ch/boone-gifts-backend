from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OccasionArchivePrompt(Base):
    """One account's answer of "not yet" to one occasion's archive nudge.

    A row exists only to record a dismissal, so `dismissed_until` is **not
    nullable**: there is no state in which the column is meaningless, and a
    nullable one would invite "row present, never dismissed" — something nothing
    needs and every reader would have to branch on.

    The snooze is dated rather than permanent. A permanent dismissal that reset
    on new activity would be the surprising option, because activity is exactly
    what happens on an occasion somebody is deliberately keeping open; the date
    lapses instead and the nudge comes back.

    `UNIQUE (user_id, occasion_id)` is what makes the write an upsert rather
    than an insert that can collide: a second "not yet" after the first has
    lapsed extends the snooze. It also says the row is **per account** — one
    member's dismissal never silences another eligible member's prompt.

    Nothing clears these rows except the three foreign-key paths that must
    (`delete_family`, `cascade_delete_user`, and the dev seed's purge).
    Archiving the occasion and leaving the family both leave the row standing:
    the eligibility query already excludes archived occasions and non-members,
    so the row is invisible rather than wrong — and it still means what the user
    meant if the occasion is unarchived or they rejoin.
    """

    __tablename__ = "occasion_archive_prompts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "occasion_id",
            name="uq_occasion_archive_prompts_user_occasion",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    occasion_id: Mapped[int] = mapped_column(ForeignKey("occasions.id"))
    dismissed_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
