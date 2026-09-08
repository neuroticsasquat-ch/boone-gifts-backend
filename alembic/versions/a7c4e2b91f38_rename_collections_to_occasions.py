"""rename collections to occasions

Revision ID: a7c4e2b91f38
Revises: d8a3f1c05b64
Create Date: 2026-09-07 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c4e2b91f38'
down_revision: Union[str, Sequence[str], None] = 'd8a3f1c05b64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # `collections` only needs its name changed, and SQLite renames a table in
    # place (>= 3.25 also rewrites the FK clause pointing at it from the items
    # table), so a plain rename is enough and preserves every row.
    op.rename_table('collections', 'occasions')

    # The items table needs its FK column *and* its unique constraint renamed
    # too. Batch mode reflects the old constraint name and would carry it
    # forward, so build the new table explicitly, copy the rows across with
    # their ids intact, and drop the old one. Nothing references
    # `collection_items`, so the drop is safe under PRAGMA foreign_keys=ON.
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
        'SELECT id, collection_id, list_id, created_at FROM collection_items'
    )
    op.drop_table('collection_items')


def downgrade() -> None:
    """Downgrade schema."""
    # Rename the parent back first: the copy below inserts rows into a table
    # whose FK points at `collections`, and PRAGMA foreign_keys=ON needs that
    # table to exist by then.
    op.rename_table('occasions', 'collections')

    op.create_table(
        'collection_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('collection_id', sa.Integer(), nullable=False),
        sa.Column('list_id', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['collection_id'], ['collections.id'], ),
        sa.ForeignKeyConstraint(['list_id'], ['lists.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'collection_id', 'list_id', name='uq_collection_items_collection_list'
        ),
    )
    op.execute(
        'INSERT INTO collection_items (id, collection_id, list_id, created_at) '
        'SELECT id, occasion_id, list_id, created_at FROM occasion_items'
    )
    op.drop_table('occasion_items')
