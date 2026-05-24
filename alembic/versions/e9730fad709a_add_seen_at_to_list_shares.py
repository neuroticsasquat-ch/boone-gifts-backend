"""add seen_at to list_shares

Revision ID: e9730fad709a
Revises: e721ca9a6ebf
Create Date: 2026-05-24 20:08:23.841997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9730fad709a'
down_revision: Union[str, Sequence[str], None] = 'e721ca9a6ebf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use ADD COLUMN directly (SQLite supports it natively for simple additions)
    # to avoid batch mode's drop/recreate which fails on FK constraints.
    op.add_column(
        'list_shares',
        sa.Column('seen_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('list_shares', schema=None) as batch_op:
        batch_op.drop_column('seen_at')
