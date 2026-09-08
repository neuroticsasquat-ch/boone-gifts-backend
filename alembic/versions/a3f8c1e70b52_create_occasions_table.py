"""create the family occasions table

Revision ID: a3f8c1e70b52
Revises: f1a6b3c80d27
Create Date: 2026-09-08 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f8c1e70b52'
down_revision: Union[str, Sequence[str], None] = 'f1a6b3c80d27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    The family-owned gifting occasion (ADR 0002). The name `occasions` was
    vacated by `c9d4e7a2f180`, which renamed the user's curated set to
    `folders` precisely so this table could claim it; the two never share a
    revision. No dates — the occasion's name bounds its period.
    """
    op.create_table(
        'occasions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column(
            'is_archived',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_occasions_family_id'), 'occasions', ['family_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_occasions_family_id'), table_name='occasions')
    op.drop_table('occasions')
