"""add recipient to lists

Revision ID: d8a3f1c05b64
Revises: c4f2a91d7e30
Create Date: 2026-09-05 22:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8a3f1c05b64'
down_revision: Union[str, Sequence[str], None] = 'c4f2a91d7e30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use ADD COLUMN directly (SQLite supports it natively for simple additions)
    # to avoid batch mode's drop/recreate which fails on FK constraints.
    # No server_default and no backfill: existing rows come out NULL, which is
    # exactly today's behaviour (no recipient).
    op.add_column(
        'lists',
        sa.Column('recipient_name', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'lists',
        sa.Column('recipient_has_account', sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # DROP COLUMN directly rather than via batch mode. Unlike `list_shares`
    # (e9730fad709a), `lists` is referenced by gifts, list_shares,
    # list_family_shares and collection_items, so batch mode's drop/recreate
    # trips PRAGMA foreign_keys=ON. SQLite has supported DROP COLUMN natively
    # since 3.35.
    op.drop_column('lists', 'recipient_has_account')
    op.drop_column('lists', 'recipient_name')
