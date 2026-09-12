"""'add list_family_shares'

Revision ID: c4f2a91d7e30
Revises: 13861325bacf
Create Date: 2026-09-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f2a91d7e30'
down_revision: Union[str, Sequence[str], None] = '13861325bacf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('list_family_shares',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('list_id', sa.Integer(), nullable=False),
    sa.Column('family_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['list_id'], ['lists.id'], ),
    sa.ForeignKeyConstraint(['family_id'], ['families.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('list_id', 'family_id', name='uq_list_family_shares_list_family')
    )
    with op.batch_alter_table('list_family_shares', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_list_family_shares_list_id'), ['list_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_list_family_shares_family_id'), ['family_id'], unique=False)

    # Backfill: preserve today's implicit "every list is visible to every family
    # the owner belongs to" so visibility after the deploy matches before it.
    # Archived lists included, deliberately.
    op.execute(
        sa.text(
            "INSERT INTO list_family_shares (list_id, family_id, created_at) "
            "SELECT l.id, fm.family_id, CURRENT_TIMESTAMP "
            "FROM lists l "
            "JOIN family_members fm ON fm.user_id = l.owner_id"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('list_family_shares', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_list_family_shares_family_id'))
        batch_op.drop_index(batch_op.f('ix_list_family_shares_list_id'))

    op.drop_table('list_family_shares')
