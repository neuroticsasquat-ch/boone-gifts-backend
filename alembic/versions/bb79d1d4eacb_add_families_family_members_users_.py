"""'add families family_members users.simple_mode'

Revision ID: bb79d1d4eacb
Revises: a1b2c3d4e5f6
Create Date: 2026-06-22 22:26:42.794834

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb79d1d4eacb'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Guarded with inspector checks so the migration is idempotent. A prior
    revision of this file contained a spurious ``op.drop_table(
    '_alembic_tmp_collections')`` (a stray autogenerate artifact) that aborted
    the migration after ``families``/``family_members`` were already created
    (SQLite auto-commits DDL). The guards below let the migration re-run
    cleanly over such a half-applied database.
    """
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if 'families' not in existing_tables:
        op.create_table('families',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'family_members' not in existing_tables:
        op.create_table('family_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('family_id', 'user_id', name='uq_family_members_family_user')
        )

    user_columns = {col['name'] for col in inspector.get_columns('users')}
    if 'simple_mode' not in user_columns:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('simple_mode', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    user_columns = {col['name'] for col in inspector.get_columns('users')}

    if 'simple_mode' in user_columns:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.drop_column('simple_mode')

    if 'family_members' in existing_tables:
        op.drop_table('family_members')
    if 'families' in existing_tables:
        op.drop_table('families')
