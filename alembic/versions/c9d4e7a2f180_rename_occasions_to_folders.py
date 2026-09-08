"""rename occasions to folders

Revision ID: c9d4e7a2f180
Revises: e2b7d4a91c53
Create Date: 2026-09-08 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d4e7a2f180'
down_revision: Union[str, Sequence[str], None] = 'e2b7d4a91c53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # This revision does nothing but vacate the name `occasions`, which a later
    # revision reuses for the family concept. The two must not share a
    # revision — see the shopping-lists project spec §11.

    # `occasions` only needs its name changed, and SQLite renames a table in
    # place (>= 3.25 also rewrites the FK clause pointing at it from the items
    # table), so a plain rename is enough and preserves every row.
    op.rename_table('occasions', 'folders')

    # The items table needs its FK column *and* its unique constraint renamed
    # too. Batch mode reflects the old constraint name and would carry it
    # forward, so build the new table explicitly, copy the rows across with
    # their ids intact, and drop the old one. Nothing references
    # `occasion_items`, so the drop is safe under PRAGMA foreign_keys=ON.
    op.create_table(
        'folder_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('folder_id', sa.Integer(), nullable=False),
        sa.Column('list_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], ),
        sa.ForeignKeyConstraint(['list_id'], ['lists.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'folder_id', 'list_id', name='uq_folder_items_folder_list'
        ),
    )
    op.execute(
        'INSERT INTO folder_items (id, folder_id, list_id, created_at) '
        'SELECT id, occasion_id, list_id, created_at FROM occasion_items'
    )
    op.drop_table('occasion_items')


def downgrade() -> None:
    """Downgrade schema."""
    # Rename the parent back first: the copy below inserts rows into a table
    # whose FK points at `occasions`, and PRAGMA foreign_keys=ON needs that
    # table to exist by then.
    op.rename_table('folders', 'occasions')

    op.create_table(
        'occasion_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('occasion_id', sa.Integer(), nullable=False),
        sa.Column('list_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['occasion_id'], ['occasions.id'], ),
        sa.ForeignKeyConstraint(['list_id'], ['lists.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'occasion_id', 'list_id', name='uq_occasion_items_occasion_list'
        ),
    )
    op.execute(
        'INSERT INTO occasion_items (id, occasion_id, list_id, created_at) '
        'SELECT id, folder_id, list_id, created_at FROM folder_items'
    )
    op.drop_table('folder_items')
