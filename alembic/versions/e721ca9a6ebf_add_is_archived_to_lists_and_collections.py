"""add is_archived to lists and collections

Revision ID: e721ca9a6ebf
Revises: 73e1a8c85058
Create Date: 2026-05-24 19:43:54.989749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e721ca9a6ebf'
down_revision: Union[str, Sequence[str], None] = '73e1a8c85058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use ADD COLUMN directly (SQLite supports it natively for simple additions)
    # to avoid batch mode's drop/recreate which fails on FK constraints.
    op.add_column(
        'collections',
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        'lists',
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('lists', schema=None) as batch_op:
        batch_op.drop_column('is_archived')

    with op.batch_alter_table('collections', schema=None) as batch_op:
        batch_op.drop_column('is_archived')
