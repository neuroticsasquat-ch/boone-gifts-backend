"""add occasion_archive_prompts table

Revision ID: f6b2c9e41a58
Revises: c1f9a7d4e260
Create Date: 2026-09-10 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6b2c9e41a58'
down_revision: Union[str, Sequence[str], None] = 'c1f9a7d4e260'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    The only revision in this project: one account's recorded "not yet" against
    one occasion's archive nudge.

    Nothing is backfilled and nothing could be. No prompt has ever been
    dismissed, and inventing a snooze would suppress a nudge the user never saw
    — the exact opposite of what the absent row means.

    `dismissed_until` is `NOT NULL` because a row exists only to record a
    dismissal: there is no state in which the column is meaningless, and a
    nullable one would invite "row present, never dismissed", which nothing
    needs and every reader would have to branch on.

    The unique constraint carries real weight rather than documenting an
    intention — it is what makes the write an upsert, so a second dismissal
    after the first has lapsed extends the snooze instead of colliding. It is
    also the statement that a prompt is *per account*: one member's dismissal
    can never silence another eligible member's.
    """
    op.create_table(
        'occasion_archive_prompts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('occasion_id', sa.Integer(), nullable=False),
        sa.Column('dismissed_until', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['occasion_id'], ['occasions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'occasion_id',
                            name='uq_occasion_archive_prompts_user_occasion'),
    )


def downgrade() -> None:
    """Downgrade schema.

    Every snooze is lost, and every suppressed nudge returns at the next read.
    There is nowhere else in the schema to keep one, and a returning prompt is
    the safe direction to fail in: the user is asked again rather than silenced
    by a row nobody can see.
    """
    op.drop_table('occasion_archive_prompts')
