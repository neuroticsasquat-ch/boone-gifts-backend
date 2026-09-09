"""add list_occasion_shares and drop list_family_shares

Revision ID: b7e2d4f16c93
Revises: a3f8c1e70b52
Create Date: 2026-09-08 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2d4f16c93'
down_revision: Union[str, Sequence[str], None] = 'a3f8c1e70b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Sharing re-points at the occasion (ADR 0002): the family is derived through
    `occasions.family_id` and is not stored twice.

    **Every existing family grant is dropped, with no backfill.** Inventing an
    occasion per family would have preserved sharing at the cost of seeding every
    family with a name nobody chose; the beta's data is explicitly resettable, so
    owners re-share instead. Note the asymmetry with the claims migration that
    follows, and do not tidy it: a dropped grant is re-created in seconds, while
    a dropped claim silently invites two people to buy the same present.
    """
    op.create_table(
        'list_occasion_shares',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('list_id', sa.Integer(), nullable=False),
        sa.Column('occasion_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['list_id'], ['lists.id'], ),
        sa.ForeignKeyConstraint(['occasion_id'], ['occasions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'list_id', 'occasion_id', name='uq_list_occasion_shares_list_occasion'
        ),
    )
    with op.batch_alter_table('list_occasion_shares', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_list_occasion_shares_list_id'), ['list_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_list_occasion_shares_occasion_id'),
            ['occasion_id'],
            unique=False,
        )

    with op.batch_alter_table('list_family_shares', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_list_family_shares_family_id'))
        batch_op.drop_index(batch_op.f('ix_list_family_shares_list_id'))
    op.drop_table('list_family_shares')


def downgrade() -> None:
    """Downgrade schema.

    `list_family_shares` comes back empty. The grants it held were dropped on the
    way up and there is nothing left to reconstruct them from — the occasion
    shares written since are a different shape, and backfilling from family
    membership would invent grants nobody made.
    """
    op.create_table(
        'list_family_shares',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('list_id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['list_id'], ['lists.id'], ),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'list_id', 'family_id', name='uq_list_family_shares_list_family'
        ),
    )
    with op.batch_alter_table('list_family_shares', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_list_family_shares_list_id'), ['list_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_list_family_shares_family_id'), ['family_id'], unique=False
        )

    with op.batch_alter_table('list_occasion_shares', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_list_occasion_shares_occasion_id'))
        batch_op.drop_index(batch_op.f('ix_list_occasion_shares_list_id'))
    op.drop_table('list_occasion_shares')
