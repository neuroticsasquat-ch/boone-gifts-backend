"""drop lists.recipient_has_account

Revision ID: e2b7d4a91c53
Revises: b5e1c7d92a04
Create Date: 2026-09-07 21:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b7d4a91c53'
down_revision: Union[str, Sequence[str], None] = 'b5e1c7d92a04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    No backfill. `recipient_has_account = true` meant "a co-resident who reads
    this list on this same login", which `account_people` now models, but those
    rows are beta test data and are not converted into account people (project
    decision 13). They simply keep their `recipient_name`, which from here means
    the one remaining thing: a person with no account.
    """
    # DROP COLUMN directly rather than via batch mode. `lists` is referenced by
    # gifts, list_shares, list_family_shares and occasion_items, so batch mode's
    # drop/recreate trips PRAGMA foreign_keys=ON — the same reason d8a3f1c05b64
    # and b5e1c7d92a04 add and drop this table's columns directly. SQLite has
    # supported DROP COLUMN natively since 3.35.
    op.drop_column('lists', 'recipient_has_account')


def downgrade() -> None:
    """Downgrade schema.

    Bare add, no backfill, matching d8a3f1c05b64 and b5e1c7d92a04 and §9's "no
    compatibility shims, no careful backfill". The dropped answers are gone, so
    every row comes back NULL — which under the pre-drop model reads as
    `kept_for_absent_person = False` on a list that carries a recipient. Reset
    the data rather than trusting a downgraded database to keep claims hidden.
    """
    op.add_column(
        'lists',
        sa.Column('recipient_has_account', sa.Boolean(), nullable=True),
    )
